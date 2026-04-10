#!/usr/bin/env python3
"""
Shared extraction step.

Why this exists:
- We do not want C++ and Rust to compete on extraction quality.
- We want one fixed extractor so the runtime comparison stays honest.
"""

from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path

import trafilatura


def read_rows(index_path: Path) -> list[dict[str, str]]:
    with index_path.open("r", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python extract_batch.py RUN_DIR", file=sys.stderr)
        return 1

    run_dir = Path(sys.argv[1]).resolve()
    index_path = run_dir / "index.tsv"
    out_path = run_dir / "extracted.tsv"
    rows = read_rows(index_path)

    char_counts: list[int] = []
    done = 0

    with out_path.open("w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["id", "url", "chars", "words", "text_path"])

        text_dir = run_dir / "text"
        text_dir.mkdir(parents=True, exist_ok=True)

        for row in rows:
            html_path = row["html_path"].strip()
            if not html_path:
                continue

            html = Path(html_path).read_text(encoding="utf-8", errors="ignore")

            # Hint: this is the only extraction algorithm in the project.
            # If you later swap it out, both runtimes still stay comparable.
            text = trafilatura.extract(html) or ""
            if not text:
                continue

            done += 1
            chars = len(text)
            words = len(text.split())
            char_counts.append(chars)

            text_path = text_dir / f"{int(row['id']):06d}.txt"
            text_path.write_text(text, encoding="utf-8")
            writer.writerow([row["id"], row["url"], chars, words, str(text_path)])

    avg_chars = statistics.fmean(char_counts) if char_counts else 0.0
    print(
        f"{run_dir.name}: extracted_docs={done} avg_chars={avg_chars:.1f} total_chars={sum(char_counts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
