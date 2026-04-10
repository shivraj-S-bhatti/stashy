# Mini Crawl Compare

Mini Crawl Compare is the smallest useful piece of Stashy.

It implements the same crawl contract twice:

- `cpp/crawl.cpp`: C++ with `libcurl` multi
- `rust/src/main.rs`: Rust with `tokio` + `reqwest`

Both runtimes fetch the same URLs, emit the same artifact format, and feed the same extractor.

## What It Does

Given a file of URLs, each runtime:

- fetches pages concurrently
- writes HTML artifacts into `RUN_DIR/html/`
- writes a matching `RUN_DIR/index.tsv`
- prints a small measured summary

Then the shared Python step:

- extracts text from the saved HTML with `trafilatura`
- writes `RUN_DIR/extracted.tsv`

Finally, the reporting step:

- compares both runs
- saves a summary table
- saves a small graph

## Shared Contract

`index.tsv` columns:

```text
id    url    final_url    status    code    ms    bytes    html_path    error
```

The contract matters because it makes the benchmark honest:

- same input set
- same saved HTML
- same extractor
- same final comparison script

Only the runtime changes.

## Layout

```text
mini_crawl_compare/
├── cpp/crawl.cpp
├── rust/Cargo.toml
├── rust/src/main.rs
├── extract_batch.py
├── compare_runs.py
├── benchmark_and_plot.py
├── requirements.txt
├── urls.txt
└── report/
    ├── comparison.png
    └── summary.tsv
```

## Setup

### Python extractor

```bash
cd mini_crawl_compare
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### C++ build

```bash
cd mini_crawl_compare
clang++ -std=c++20 -O3 cpp/crawl.cpp $(curl-config --cflags --libs) -o cpp/crawl_cpp
```

### Rust build

```bash
cd mini_crawl_compare/rust
cargo build --release
```

## Running

### C++

```bash
cd mini_crawl_compare
./cpp/crawl_cpp urls.txt runs/cpp 8
```

### Rust

```bash
cd mini_crawl_compare/rust
cargo run --release -- ../urls.txt ../runs/rust 8
```

### Shared extraction

```bash
cd mini_crawl_compare
source .venv/bin/activate
python extract_batch.py runs/cpp
python extract_batch.py runs/rust
```

### Quick comparison

```bash
cd mini_crawl_compare
python compare_runs.py runs/cpp runs/rust
```

### Full benchmark + graph

```bash
cd mini_crawl_compare
python benchmark_and_plot.py
```

## Teaching Notes

This project is intentionally designed to be rewritten from scratch while learning:

- the source files are short
- the artifact boundary is explicit
- comments explain the role of each moving part
- the runtime policy is simple enough to explain in a short video

If you are learning both languages, a good sequence is:

1. read the shared contract
2. reimplement the C++ version
3. reimplement the Rust version
4. rerun the same benchmark
5. inspect how the numbers change

## Performance Topics To Study With It

This tiny project is a good sandbox for:

- concurrency limits and backpressure
- async event loops versus higher-level runtimes
- response-buffer lifetime and memory pressure
- tail latency versus average latency
- reproducible benchmarking on fixed workloads
- profiling before and after a change

If you want to connect it to a performance engineering course, the cleanest story is:

- use the current version as a baseline
- make one systems change at a time
- rerun the same benchmark
- explain the result using queueing, locality, or synchronization reasoning rather than guesswork

## Next Small Extension

If you want one additional systems feature without turning this into a full crawler framework:

- add a cheap `needs_browser` decision
- route only suspicious pages to a browser fallback lane

That keeps the project small while moving it closer to a real crawl scheduler.
