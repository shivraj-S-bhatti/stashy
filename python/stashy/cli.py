"""CLI: enqueue seed URLs for the crawler."""
from __future__ import annotations

import argparse
import asyncio

from .db import close_pool, enqueue_url, get_pool


async def enqueue_urls(urls: list[str], priority: int = 0) -> None:
    await get_pool()
    inserted = 0
    for url in urls:
        clean = url.strip()
        if not clean:
            continue
        ok = await enqueue_url(clean, priority=priority, source="seed", depth=0)
        if ok:
            inserted += 1
        print(f"  {'+ ' if ok else '  (skip) '}{clean}")
    await close_pool()
    print(f"Inserted {inserted}/{len(urls)} seed URLs")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enqueue seed URLs into stashy")
    parser.add_argument("urls", nargs="+", help="One or more seed URLs")
    parser.add_argument("--priority", type=int, default=0, help="Queue priority for all URLs")
    args = parser.parse_args()

    asyncio.run(enqueue_urls(args.urls, priority=args.priority))


if __name__ == "__main__":
    main()
