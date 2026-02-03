"""CLI: enqueue seed URLs for the crawler."""
import asyncio
import sys
from .config import get_database_url
from .db import enqueue_url, get_pool, close_pool


async def enqueue_urls(urls: list[str], priority: int = 0) -> None:
    await get_pool()
    for url in urls:
        ok = await enqueue_url(url.strip(), priority=priority)
        print(f"  {'+ ' if ok else '  (skip) '}{url}")
    await close_pool()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m stashy.cli <url1> [url2 ...]")
        sys.exit(1)
    urls = sys.argv[1:]
    asyncio.run(enqueue_urls(urls))


if __name__ == "__main__":
    main()
