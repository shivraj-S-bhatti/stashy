"""Fault-tolerant crawler worker: claim URLs, fetch with Playwright, extract with LLM, store in PostgreSQL."""
from __future__ import annotations

import asyncio
import logging
import os
import signal

from .config import get_batch_size, get_worker_id
from .crawler import get_page_html
from .db import (
    claim_pending_urls,
    close_pool,
    get_pool,
    insert_extraction,
    insert_raw_page,
    mark_url_done,
    mark_url_failed,
)
from .dom_analyzer import analyze_dom_with_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stashy.worker")

POLL_INTERVAL = 2.0
RUN = True


def _shutdown(*_):
    global RUN
    RUN = False


async def process_one(url_id: int, url: str) -> None:
    """Fetch URL with Playwright, run LLM DOM analysis, persist page and extraction."""
    try:
        html, status_code, content_type = await get_page_html(url)
    except Exception as e:
        await mark_url_failed(url_id, str(e))
        logger.warning("Fetch failed %s: %s", url, e)
        return
    if html is None:
        await mark_url_failed(url_id, "fetch failed or timeout")
        logger.warning("No HTML for %s", url)
        return
    try:
        page_id = await insert_raw_page(url_id, url, html, status_code, content_type)
    except Exception as e:
        await mark_url_failed(url_id, str(e))
        logger.warning("Insert raw_page failed %s: %s", url, e)
        return
    try:
        payload, confidence = analyze_dom_with_llm(html, url)
        await insert_extraction(url_id, page_id, "default", payload, confidence)
    except Exception as e:
        logger.warning("Extraction failed %s: %s", url, e)
        # Still mark URL done; we have raw page
    await mark_url_done(url_id)
    logger.info("Done %s (url_id=%s)", url[:80], url_id)


async def run_worker() -> None:
    worker_id = get_worker_id()
    batch_size = get_batch_size()
    logger.info("Worker %s starting, batch_size=%s", worker_id, batch_size)
    await get_pool()
    while RUN:
        try:
            rows = await claim_pending_urls(worker_id, batch_size)
        except Exception as e:
            logger.exception("Claim failed: %s", e)
            await asyncio.sleep(POLL_INTERVAL)
            continue
        if not rows:
            await asyncio.sleep(POLL_INTERVAL)
            continue
        for row in rows:
            if not RUN:
                break
            await process_one(row["id"], row["url"])
    await close_pool()
    logger.info("Worker %s stopped", worker_id)


def main() -> None:
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
