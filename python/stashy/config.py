"""Configuration from environment."""
from __future__ import annotations

import os


def get_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://crawler:crawler@localhost:5432/crawler",
    )


def get_llm_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY")


def get_llm_base_url() -> str | None:
    return os.environ.get("LLM_API_BASE")


def get_crawl_concurrency() -> int:
    return int(os.environ.get("CRAWL_CONCURRENCY", "4"))


def get_worker_id() -> str:
    return os.environ.get("WORKER_ID", f"worker-{os.getpid()}")


def get_batch_size() -> int:
    return int(os.environ.get("CLAIM_BATCH_SIZE", "10"))


def get_frontier_max_links() -> int:
    return int(os.environ.get("FRONTIER_MAX_LINKS", "16"))


def get_frontier_max_depth() -> int:
    return int(os.environ.get("FRONTIER_MAX_DEPTH", "2"))


def get_geo_score_threshold() -> float:
    return float(os.environ.get("GEO_SCORE_THRESHOLD", "0.28"))


def get_metrics_flush_every() -> int:
    return int(os.environ.get("METRICS_FLUSH_EVERY", "15"))
