"""Configuration from environment."""
import os
from urllib.parse import urlparse

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
