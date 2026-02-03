# Stashy — AI-Driven Universal Web Crawler

High-performance, fault-tolerant web crawler with **LangChain** and **Playwright** for agentic crawling and **LLM-based DOM pattern analysis** for high extraction accuracy. A **C++** engine handles async I/O and throughput (15K+ pages/min); **PostgreSQL** backs the distributed pipeline (2M+ pages/day).

## Architecture

- **Python (Agentic Crawler)**: LangChain + Playwright agent, LLM DOM pattern analysis for extraction.
- **C++ Engine**: Async I/O, URL queue consumption, high-throughput fetch and dispatch.
- **PostgreSQL**: URL queue, raw pages, extraction results, and job state.

## Prerequisites

- Docker & Docker Compose (for PostgreSQL)
- Python 3.11+ (`python3 -m pip install -e python/`)
- C++17 compiler (Clang/GCC), CMake 3.16+, libpq (PostgreSQL client), libcurl (for C++ engine)
- OpenAI API key (optional; for LLM DOM analysis; fallback extraction without it)

## Quick Start

```bash
# Start PostgreSQL
docker compose up -d postgres

# Python: install and run crawler worker
cd python && pip install -r requirements.txt && playwright install chromium
export DATABASE_URL=postgresql://crawler:crawler@localhost:5432/crawler
export OPENAI_API_KEY=sk-...
python -m stashy.worker

# C++: build and run engine (high-throughput fetch; requires CMake, libpq, libcurl)
# macOS: brew install cmake libpq curl
mkdir cpp/build && cd cpp/build && cmake .. && make
./stashy_engine --db postgresql://crawler:crawler@localhost:5432/crawler --workers 16
```

## Project Layout

```
stashy/
├── python/           # LangChain + Playwright agent, LLM DOM extraction
├── cpp/              # High-performance async engine
├── db/               # PostgreSQL schema and migrations
├── docker-compose.yml
└── README.md
```

## Configuration

- `DATABASE_URL`: PostgreSQL connection string.
- `OPENAI_API_KEY`: For LLM DOM pattern analysis (or set `LLM_API_BASE` for compatible APIs).
- `CRAWL_CONCURRENCY`: Number of concurrent Playwright browsers (default 4).

## License

MIT
