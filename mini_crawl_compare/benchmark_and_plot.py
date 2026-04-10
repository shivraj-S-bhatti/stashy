#!/usr/bin/env python3
"""
Run both implementations, compute comparable metrics, and save a small chart.

Why this script exists:
- You want one repeatable command for the demo.
- The graph should come from measured runs, not hand-written numbers.
"""

from __future__ import annotations

import csv
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))
os.environ.setdefault("MPLBACKEND", "Agg")
(ROOT / ".mplconfig").mkdir(exist_ok=True)
(ROOT / ".cache").mkdir(exist_ok=True)

import matplotlib.pyplot as plt


LINE_RE = re.compile(
    r"(?P<name>cpp|rust)\s+fetched=(?P<fetched>\d+)/(?P<total>\d+)\s+"
    r"avg_ms=(?P<avg_ms>[0-9.]+)\s+p95_ms=(?P<p95_ms>[0-9.]+)\s+"
    r"pages_per_sec=(?P<pps>[0-9.]+)\s+total_bytes=(?P<bytes>\d+)"
)


def run(cmd: list[str], cwd: Path) -> str:
    # Hint: capture stdout so we can parse the measured metrics directly.
    out = subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True, env=os.environ.copy())
    return out.stdout.strip()


def extractor_python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def rust_run_prefix() -> list[str]:
    local_rustup = ROOT / ".cargo" / "bin" / "rustup"
    if local_rustup.exists():
        os.environ.setdefault("RUSTUP_HOME", str(ROOT / ".rustup"))
        os.environ.setdefault("CARGO_HOME", str(ROOT / ".cargo"))
        return [str(local_rustup), "run", "stable", "cargo"]
    return ["cargo"]


def parse_runtime_line(line: str) -> dict[str, float | int | str]:
    m = LINE_RE.search(line)
    if not m:
        raise ValueError(f"could not parse runtime output: {line}")
    row: dict[str, float | int | str] = {
        "name": m.group("name"),
        "fetched": int(m.group("fetched")),
        "total": int(m.group("total")),
        "avg_ms": float(m.group("avg_ms")),
        "p95_ms": float(m.group("p95_ms")),
        "pages_per_sec": float(m.group("pps")),
        "total_bytes": int(m.group("bytes")),
    }
    row["pages_per_min"] = row["pages_per_sec"] * 60.0
    row["pages_per_day"] = row["pages_per_sec"] * 86400.0
    seconds = row["fetched"] / row["pages_per_sec"] if row["pages_per_sec"] else 0.0
    row["mb_per_sec"] = (row["total_bytes"] / max(seconds, 1e-9)) / (1024.0 * 1024.0)
    return row


def extract(run_dir: Path) -> tuple[int, int]:
    run([extractor_python(), "extract_batch.py", str(run_dir)], ROOT)
    rows = []
    with (run_dir / "extracted.tsv").open("r", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    total_chars = sum(int(r["chars"]) for r in rows)
    return len(rows), total_chars


def write_summary(rows: list[dict[str, float | int | str]], path: Path) -> None:
    fieldnames = [
        "name",
        "fetched",
        "total",
        "avg_ms",
        "p95_ms",
        "pages_per_sec",
        "pages_per_min",
        "pages_per_day",
        "mb_per_sec",
        "total_bytes",
        "extracted_docs",
        "total_chars",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def make_plot(rows: list[dict[str, float | int | str]], path: Path) -> None:
    names = [str(r["name"]).upper() for r in rows]
    colors = ["#ffb86c", "#8be9fd"]

    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    fig.patch.set_facecolor("#fffaf2")
    for ax in axes.flat:
        ax.set_facecolor("#fffdf8")
        ax.grid(axis="y", alpha=0.22, linestyle="--")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    metrics = [
        ("pages_per_sec", "Pages / sec", False),
        ("pages_per_day", "Pages / day (extrapolated)", False),
        ("avg_ms", "Average latency ms", True),
        ("p95_ms", "P95 latency ms", True),
    ]

    for ax, (key, label, lower_better) in zip(axes.flat, metrics):
        vals = [float(r[key]) for r in rows]
        bars = ax.bar(names, vals, color=colors, width=0.58, edgecolor="#444", linewidth=0.8)
        ax.set_title(label, fontsize=11, pad=10)
        for bar, val in zip(bars, vals):
            text = f"{val:,.1f}" if val < 10000 else f"{val:,.0f}"
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                bar.get_height(),
                text,
                ha="center",
                va="bottom",
                fontsize=9,
            )
        if lower_better:
            ax.text(0.02, 0.95, "lower is better", transform=ax.transAxes, va="top", fontsize=8, color="#666")
        else:
            ax.text(0.02, 0.95, "higher is better", transform=ax.transAxes, va="top", fontsize=8, color="#666")

    equal_chars = all(int(r["total_chars"]) == int(rows[0]["total_chars"]) for r in rows)
    subtitle = "Shared extractor held constant"
    if equal_chars:
        subtitle += f" • both produced {int(rows[0]['total_chars']):,} extracted chars"

    fig.suptitle("Mini Crawl Compare", fontsize=16, y=0.98)
    fig.text(0.5, 0.94, subtitle, ha="center", fontsize=10, color="#555")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> int:
    cpp_out = run(["./cpp/crawl_cpp", "urls.txt", "runs/cpp", "8"], ROOT)
    rust_out = run(rust_run_prefix() + ["run", "--release", "--", "../urls.txt", "../runs/rust", "8"], ROOT / "rust")

    rows = [parse_runtime_line(cpp_out), parse_runtime_line(rust_out)]

    for row in rows:
        run_dir = ROOT / "runs" / str(row["name"])
        extracted_docs, total_chars = extract(run_dir)
        row["extracted_docs"] = extracted_docs
        row["total_chars"] = total_chars

    out_dir = ROOT / "report"
    out_dir.mkdir(exist_ok=True)
    write_summary(rows, out_dir / "summary.tsv")
    make_plot(rows, out_dir / "comparison.png")

    print("name\tpages/sec\tpages/min\tpages/day\tavg_ms\tp95_ms\tMB/sec\textracted_docs\ttotal_chars")
    for row in rows:
        print(
            f"{row['name']}\t{float(row['pages_per_sec']):.2f}\t{float(row['pages_per_min']):.1f}\t"
            f"{float(row['pages_per_day']):.0f}\t{float(row['avg_ms']):.1f}\t{float(row['p95_ms']):.1f}\t"
            f"{float(row['mb_per_sec']):.3f}\t{int(row['extracted_docs'])}\t{int(row['total_chars'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
