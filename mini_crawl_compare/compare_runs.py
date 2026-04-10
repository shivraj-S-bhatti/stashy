#!/usr/bin/env python3
"""Tiny summary script for side-by-side run directories."""

from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def p95(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[int(0.95 * (len(values) - 1))]


def summarize(run_dir: Path) -> dict[str, float | str]:
    index_rows = read_tsv(run_dir / "index.tsv")
    extract_rows = read_tsv(run_dir / "extracted.tsv")

    ms = [float(r["ms"]) for r in index_rows if r["ms"]]
    sizes = [int(r["bytes"]) for r in index_rows if r["bytes"]]
    ok = [r for r in index_rows if r["status"] == "ok"]
    extracted_chars = [int(r["chars"]) for r in extract_rows if r["chars"]]

    return {
        "run": run_dir.name,
        "fetched": len(ok),
        "total_urls": len(index_rows),
        "avg_ms": statistics.fmean(ms) if ms else 0.0,
        "p95_ms": p95(ms),
        "total_bytes": sum(sizes),
        "extracted_docs": len(extract_rows),
        "total_chars": sum(extracted_chars),
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python compare_runs.py RUN_DIR...", file=sys.stderr)
        return 1

    rows = [summarize(Path(arg).resolve()) for arg in sys.argv[1:]]

    print(
        "run\tfetched/total\tavg_ms\tp95_ms\ttotal_bytes\textracted_docs\ttotal_chars"
    )
    for row in rows:
        print(
            f"{row['run']}\t{row['fetched']}/{row['total_urls']}\t"
            f"{row['avg_ms']:.1f}\t{row['p95_ms']:.1f}\t{row['total_bytes']}\t"
            f"{row['extracted_docs']}\t{row['total_chars']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
