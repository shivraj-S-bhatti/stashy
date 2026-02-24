# STASHY Spatial Ingestion Fabric

**High-throughput geospatial data ingestion platform with agentic frontier expansion, adaptive scheduling, and measurable infrastructure impact.**

STASHY is a deep dive in in:
- AI infrastructure
- distributed systems
- geospatial machine learning
- applied computer vision infrastructure
- backend data platforms

## Search-Optimized Summary

If you are looking for a **geospatial AI infrastructure project**, **distributed crawler architecture**, **adaptive queue scheduling**, **LLM-assisted extraction pipeline**, or **high-signal systems engineering **, this repo is built for that audience.

### SEO Keywords
`geospatial ai infrastructure`, `distributed crawler`, `agentic web search`, `adaptive data ingestion`, `llm extraction pipeline`, `queue scheduling`, `gpu data routing`, `foundation model data pipeline`, `postgres skip locked`, `systems design project`

## What This Project Demonstrates

1. **Distributed ingestion core**
- Lock-safe queue claiming with PostgreSQL (`FOR UPDATE SKIP LOCKED`)
- Retry and failure semantics for fault tolerance

2. **Agentic frontier expansion**
- Pages are parsed and scored for geospatial relevance
- High-value links are recursively discovered and re-enqueued with dynamic priority

3. **Adaptive scheduling strategy**
- Queue rank blends static priority + dynamic geospatial score
- Keeps processing focused on high-information pages under load

4. **Observability for infra decisions**
- Worker metrics: latency, frontier fanout, queue depth, processed vs failed
- Supports benchmarking and operational tuning

5. **Deterministic benchmark mode**
- Synthetic infra simulation comparing FIFO vs adaptive routing
- Reports throughput, freshness, latency, information gain, and uncertainty reduction

## Architecture

```mermaid
flowchart LR
  A["Seed URLs"] --> B["url_queue (priority + geo_score)"]
  B --> C["Distributed Workers"]
  C --> D["Playwright Fetch"]
  D --> E["LLM/Heuristic DOM Analyzer"]
  E --> F["Structured Extraction + Geo Signals"]
  E --> G["Frontier Candidate Scorer"]
  G --> B
  C --> H["worker_metrics"]
```

## Quick Demo (No Database Needed)

```bash
cd python
python -m stashy.infra_demo --ticks 220 --regions 30 --workers 10 --trials 4 --seed 2026
```

Expected outcome: adaptive routing should outperform FIFO on throughput/freshness while lowering world uncertainty.

## Full Stack Run (PostgreSQL + Worker)

### 1) Start database
```bash
docker compose up -d postgres
```

### 2) Install runtime
```bash
cd python
pip install -r requirements.txt
pip install -e .
playwright install chromium
```

### 3) Set environment
```bash
export DATABASE_URL=postgresql://crawler:crawler@localhost:5432/crawler
export OPENAI_API_KEY=sk-...         # optional; fallback extraction works without this
export FRONTIER_MAX_LINKS=16
export FRONTIER_MAX_DEPTH=2
export GEO_SCORE_THRESHOLD=0.28
export CLAIM_BATCH_SIZE=10
```

### 4) Enqueue seed URLs
```bash
python -m stashy.cli --priority 20 https://en.wikipedia.org/wiki/Photogrammetry https://en.wikipedia.org/wiki/Visual_positioning_system
```

### 5) Run worker
```bash
python -m stashy.worker
```

## Common FAQs

### What makes this more than a normal crawler?
STASHY does not just fetch pages. It continuously decides what to process next using relevance and infrastructure-aware prioritization.

### Why is adaptive queueing important for AI systems?
Data pipelines often bottleneck model quality. If low-value pages dominate the queue, expensive compute is wasted.

### Does this require an LLM API key?
No. LLM extraction is optional. The system falls back to heuristic extraction and still runs end-to-end.

### What problem does `geo_score` solve?
It approximates expected training utility from a page, letting the queue prioritize likely high-signal data.

### Is this production-grade or just a toy?
It is a POC with production-style patterns: explicit schema design, lock-safe claiming, retries, metrics, and deterministic benchmarking.

### Why include a simulation benchmark?
It gives reproducible evidence for scheduling policy impact without requiring external datasets or massive compute.

### What signals are used for frontier expansion?
Keyword density, host affinity, structured-data hints, freshness signals, and link-context heuristics.

### How can this be extended?
Add domain-specific parsers, Kubernetes worker autoscaling, vectorized deduplication, and reinforcement-learned scheduling policies.

### Is this relevant for backend-only roles?
Yes. The core value is queue architecture, fault tolerance, ranking policy, and observability.

### Is this relevant for CV/3D teams?
Yes. It addresses upstream ingestion quality for localization, reconstruction, and map-understanding workflows.

## File Map

- `python/stashy/worker.py`: adaptive worker loop + frontier expansion + metrics
- `python/stashy/frontier.py`: geospatial scoring and candidate ranking
- `python/stashy/dom_analyzer.py`: extraction and structured signal generation
- `python/stashy/infra_demo.py`: deterministic infrastructure benchmark
- `python/stashy/db.py`: async PostgreSQL operations
- `db/init.sql`: queue schema, functions, and metrics tables
- `llm.text`: machine-friendly project summary and FAQ for agentic retrieval

## Notes for Visitors

- This repository is intentionally optimized to show **technical depth + measurable outcomes**.
- It is suitable for demo videos, benchmark screenshots, and architecture walkthroughs.
