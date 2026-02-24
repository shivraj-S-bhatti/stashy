"""Fault-tolerant worker with adaptive frontier expansion and metrics emission."""
from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass

from .config import (
    get_batch_size,
    get_frontier_max_depth,
    get_frontier_max_links,
    get_geo_score_threshold,
    get_metrics_flush_every,
    get_worker_id,
)
from .crawler import get_page_html
from .db import (
    claim_pending_urls,
    close_pool,
    get_pool,
    insert_extraction,
    insert_raw_page,
    mark_url_done,
    mark_url_failed,
    queue_depth,
    record_worker_metrics,
    upsert_discovered_url,
)
from .dom_analyzer import analyze_dom_with_llm
from .frontier import compute_geo_signals, frontier_candidates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stashy.worker")

POLL_INTERVAL = 2.0
RUN = True


def _shutdown(*_):
    global RUN
    RUN = False


@dataclass
class WorkerCounters:
    processed: int = 0
    failed: int = 0
    frontier_enqueued: int = 0
    frontier_new: int = 0


@dataclass
class WorkerRuntime:
    latencies_ms: list[float]


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(0.95 * (len(ordered) - 1))
    return ordered[idx]


async def _enqueue_frontier(
    *,
    parent_url_id: int,
    parent_url: str,
    payload: dict,
    html: str,
    page_geo_score: float,
    current_depth: int,
    max_depth: int,
    max_links: int,
    min_geo_score: float,
    counters: WorkerCounters,
) -> int:
    candidates = frontier_candidates(
        parent_url=parent_url,
        payload=payload,
        html=html,
        current_depth=current_depth,
        max_depth=max_depth,
        max_links=max_links,
        page_geo_score=page_geo_score,
    )

    enqueued = 0
    for cand in candidates:
        if cand.geo_score < min_geo_score:
            continue
        inserted = await upsert_discovered_url(
            parent_url_id=parent_url_id,
            url=cand.url,
            priority=cand.priority,
            geo_score=cand.geo_score,
            source=f"frontier:{cand.reason}",
            depth=current_depth + 1,
        )
        counters.frontier_enqueued += 1
        if inserted:
            counters.frontier_new += 1
        enqueued += 1
    return enqueued


async def _record_metrics(worker_id: str, counters: WorkerCounters, runtime: WorkerRuntime) -> None:
    avg_latency = sum(runtime.latencies_ms) / len(runtime.latencies_ms) if runtime.latencies_ms else 0.0
    pending_depth = await queue_depth()
    await record_worker_metrics(
        worker_id=worker_id,
        processed_count=counters.processed,
        failed_count=counters.failed,
        frontier_enqueued=counters.frontier_enqueued,
        avg_latency_ms=avg_latency,
        p95_latency_ms=_p95(runtime.latencies_ms),
        current_queue_depth=pending_depth,
    )


async def process_one(row: dict, counters: WorkerCounters, runtime: WorkerRuntime) -> None:
    url_id = int(row["id"])
    url = str(row["url"])
    depth = int(row.get("depth") or 0)

    start = time.perf_counter()

    try:
        html, status_code, content_type = await get_page_html(url)
    except Exception as exc:
        counters.failed += 1
        await mark_url_failed(url_id, str(exc))
        logger.warning("Fetch failed %s: %s", url, exc)
        return

    if html is None:
        counters.failed += 1
        await mark_url_failed(url_id, "fetch failed or timeout")
        logger.warning("No HTML for %s", url)
        return

    try:
        page_id = await insert_raw_page(url_id, url, html, status_code, content_type)
    except Exception as exc:
        counters.failed += 1
        await mark_url_failed(url_id, f"insert raw_page failed: {exc}")
        logger.warning("Insert raw_page failed %s: %s", url, exc)
        return

    try:
        payload, confidence = analyze_dom_with_llm(html, url)
    except Exception as exc:
        counters.failed += 1
        await mark_url_failed(url_id, f"dom analysis failed: {exc}")
        logger.warning("Extraction failed %s: %s", url, exc)
        return

    geo_signals = compute_geo_signals(url, payload)
    page_geo_score = geo_signals.aggregate_score

    try:
        await insert_extraction(
            url_id,
            page_id,
            "spatial-default-v2",
            payload,
            confidence,
            geo_score=page_geo_score,
            signals={
                "geo_term_density": geo_signals.geo_term_density,
                "freshness_signal": geo_signals.freshness_signal,
                "structured_data_signal": geo_signals.structured_data_signal,
                "link_quality_signal": geo_signals.link_quality_signal,
            },
        )
    except Exception as exc:
        counters.failed += 1
        await mark_url_failed(url_id, f"insert extraction failed: {exc}")
        logger.warning("Insert extraction failed %s: %s", url, exc)
        return

    try:
        frontier_count = await _enqueue_frontier(
            parent_url_id=url_id,
            parent_url=url,
            payload=payload,
            html=html,
            page_geo_score=page_geo_score,
            current_depth=depth,
            max_depth=get_frontier_max_depth(),
            max_links=get_frontier_max_links(),
            min_geo_score=get_geo_score_threshold(),
            counters=counters,
        )
    except Exception as exc:
        frontier_count = 0
        logger.warning("Frontier enqueue failed for %s: %s", url, exc)

    await mark_url_done(url_id)
    counters.processed += 1

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    runtime.latencies_ms.append(elapsed_ms)

    logger.info(
        "Done %s (url_id=%s depth=%s geo=%.3f frontier=%s latency=%.1fms)",
        url[:120],
        url_id,
        depth,
        page_geo_score,
        frontier_count,
        elapsed_ms,
    )


async def run_worker() -> None:
    worker_id = get_worker_id()
    batch_size = get_batch_size()
    metrics_every = max(1, get_metrics_flush_every())

    logger.info(
        "Worker %s starting batch_size=%s max_depth=%s frontier_links=%s min_geo=%.2f",
        worker_id,
        batch_size,
        get_frontier_max_depth(),
        get_frontier_max_links(),
        get_geo_score_threshold(),
    )

    await get_pool()

    counters = WorkerCounters()
    runtime = WorkerRuntime(latencies_ms=[])

    while RUN:
        try:
            rows = await claim_pending_urls(worker_id, batch_size)
        except Exception as exc:
            logger.exception("Claim failed: %s", exc)
            await asyncio.sleep(POLL_INTERVAL)
            continue

        if not rows:
            if counters.processed and counters.processed % metrics_every == 0:
                try:
                    await _record_metrics(worker_id, counters, runtime)
                except Exception as exc:
                    logger.warning("Metrics flush failed: %s", exc)
            await asyncio.sleep(POLL_INTERVAL)
            continue

        for row in rows:
            if not RUN:
                break
            await process_one(row, counters, runtime)

            if counters.processed and counters.processed % metrics_every == 0:
                try:
                    await _record_metrics(worker_id, counters, runtime)
                    logger.info(
                        "Metrics flushed processed=%s failed=%s frontier_new=%s",
                        counters.processed,
                        counters.failed,
                        counters.frontier_new,
                    )
                except Exception as exc:
                    logger.warning("Metrics flush failed: %s", exc)

    try:
        await _record_metrics(worker_id, counters, runtime)
    except Exception as exc:
        logger.warning("Final metrics flush failed: %s", exc)

    await close_pool()
    logger.info(
        "Worker %s stopped processed=%s failed=%s frontier_enqueued=%s frontier_new=%s",
        worker_id,
        counters.processed,
        counters.failed,
        counters.frontier_enqueued,
        counters.frontier_new,
    )


def main() -> None:
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
