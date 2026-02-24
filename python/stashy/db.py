"""Async PostgreSQL access: adaptive frontier queue, raw pages, extractions, metrics."""
from __future__ import annotations

from typing import Any, Iterable

import asyncpg

from .config import get_database_url

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            get_database_url(),
            min_size=2,
            max_size=20,
            command_timeout=60,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def claim_pending_urls(worker_id: str, batch_size: int = 10) -> list[dict[str, Any]]:
    """Claim up to batch_size pending URLs for this worker."""
    pool = await get_pool()
    rows = await pool.fetch("SELECT * FROM claim_pending_urls($1, $2)", worker_id, batch_size)
    return [dict(r) for r in rows]


async def mark_url_done(url_id: int) -> None:
    pool = await get_pool()
    await pool.execute(
        """UPDATE url_queue
           SET status = 'done', claimed_at = NULL, claimed_by = NULL, processed_at = now()
           WHERE id = $1""",
        url_id,
    )


async def mark_url_failed(url_id: int, error: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """UPDATE url_queue
           SET status = CASE WHEN retries + 1 >= max_retries THEN 'failed' ELSE 'pending' END,
               retries = retries + 1,
               claimed_at = NULL,
               claimed_by = NULL,
               error = $2,
               updated_at = now()
           WHERE id = $1""",
        url_id,
        error[:4096],
    )


async def insert_raw_page(
    url_id: int,
    url: str,
    html: str | None,
    status_code: int | None,
    content_type: str | None,
) -> int:
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO raw_pages (url_id, url, html, status_code, content_type)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (url_id)
           DO UPDATE SET html = $3, status_code = $4, content_type = $5, fetched_at = now()
           RETURNING id""",
        url_id,
        url,
        html,
        status_code,
        content_type,
    )
    return int(row["id"])


async def insert_extraction(
    url_id: int,
    page_id: int,
    schema_name: str | None,
    payload: dict[str, Any],
    confidence: float | None,
    *,
    geo_score: float | None = None,
    signals: dict[str, Any] | None = None,
) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO extractions (url_id, page_id, schema_name, payload, confidence, geo_score, signals)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           ON CONFLICT (url_id)
           DO UPDATE SET
             page_id = $2,
             schema_name = $3,
             payload = $4,
             confidence = $5,
             geo_score = $6,
             signals = $7,
             extracted_at = now()""",
        url_id,
        page_id,
        schema_name,
        payload,
        confidence,
        geo_score,
        signals,
    )


async def enqueue_url(
    url: str,
    priority: int = 0,
    *,
    geo_score: float = 0.0,
    source: str = "seed",
    depth: int = 0,
) -> bool:
    """Add URL to queue if not present; returns True on insert."""
    pool = await get_pool()
    row = await pool.fetchrow(
        """INSERT INTO url_queue (url, priority, geo_score, source, depth)
           VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT (url) DO NOTHING
           RETURNING id""",
        url,
        priority,
        max(0.0, min(1.0, geo_score)),
        source,
        max(0, depth),
    )
    return row is not None


async def upsert_discovered_url(
    *,
    parent_url_id: int,
    url: str,
    priority: int,
    geo_score: float,
    source: str,
    depth: int,
) -> bool:
    pool = await get_pool()
    value = await pool.fetchval(
        "SELECT upsert_discovered_url($1, $2, $3, $4, $5, $6)",
        parent_url_id,
        url,
        priority,
        max(0.0, min(1.0, geo_score)),
        source,
        max(0, depth),
    )
    return bool(value)


async def queue_depth(statuses: Iterable[str] = ("pending", "in_progress")) -> int:
    pool = await get_pool()
    rows = list(statuses)
    return int(
        await pool.fetchval("SELECT COUNT(*)::INT FROM url_queue WHERE status = ANY($1::text[])", rows)
    )


async def record_worker_metrics(
    *,
    worker_id: str,
    processed_count: int,
    failed_count: int,
    frontier_enqueued: int,
    avg_latency_ms: float,
    p95_latency_ms: float,
    current_queue_depth: int,
) -> None:
    pool = await get_pool()
    await pool.execute(
        "SELECT record_worker_metrics($1, $2, $3, $4, $5, $6, $7)",
        worker_id,
        processed_count,
        failed_count,
        frontier_enqueued,
        avg_latency_ms,
        p95_latency_ms,
        current_queue_depth,
    )
