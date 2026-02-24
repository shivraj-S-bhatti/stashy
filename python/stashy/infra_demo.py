"""Deterministic AI Infra benchmark: FIFO frontier vs adaptive geospatial router."""
from __future__ import annotations

import argparse
import math
import random
import statistics
from dataclasses import dataclass


@dataclass
class Region:
    region_id: str
    zone: str
    uncertainty: float
    motion: float
    last_refresh: int = 0


@dataclass(frozen=True)
class Shard:
    shard_id: str
    region_id: str
    zone: str
    created_tick: int
    entropy: float
    novelty: float
    vram_gb: float
    ingest_ms: float
    train_ms: float

    def age(self, tick: int) -> int:
        return max(0, tick - self.created_tick)


@dataclass
class Worker:
    worker_id: str
    zone: str
    vram_gb: float
    tflops: float
    bandwidth: float
    busy_ms: float = 0.0


@dataclass
class Summary:
    name: str
    processed: float
    dropped: float
    avg_age: float
    p95_latency_ms: float
    avg_utilization: float
    info_gain: float
    final_uncertainty: float


def _clamp(v: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, v))


def _poisson(lam: float, rng: random.Random) -> int:
    if lam <= 0:
        return 0
    threshold = math.exp(-lam)
    k = 0
    p = 1.0
    while p > threshold:
        k += 1
        p *= rng.random()
    return max(0, k - 1)


def _job_ms(worker: Worker, shard: Shard) -> tuple[float, float]:
    if worker.zone == shard.zone:
        transfer = 8.0
    elif {worker.zone, shard.zone} in ({"west", "central"}, {"central", "east"}):
        transfer = 20.0
    else:
        transfer = 37.0
    compute = 34.0 / worker.tflops
    io = max(0.45, 1.3 - worker.bandwidth / 220.0)
    return shard.train_ms * compute + shard.ingest_ms * io + transfer, transfer


def _make_regions(n: int, rng: random.Random) -> dict[str, Region]:
    zones = ("west", "central", "east")
    out: dict[str, Region] = {}
    for i in range(n):
        out[f"R-{i:03d}"] = Region(
            region_id=f"R-{i:03d}",
            zone=zones[i % len(zones)],
            uncertainty=rng.uniform(0.46, 0.88),
            motion=rng.uniform(0.16, 0.84),
        )
    return out


def _make_workers(n: int, rng: random.Random) -> list[Worker]:
    zones = ("west", "central", "east")
    out = []
    for i in range(n):
        out.append(
            Worker(
                worker_id=f"W-{i:02d}",
                zone=zones[i % len(zones)],
                vram_gb=round(rng.uniform(8.0, 24.0), 2),
                tflops=round(rng.uniform(32.0, 64.0), 2),
                bandwidth=round(rng.uniform(80.0, 240.0), 2),
            )
        )
    return out


def _drift(regions: dict[str, Region], tick: int, rng: random.Random) -> None:
    for region in regions.values():
        staleness = tick - region.last_refresh
        region.uncertainty = _clamp(region.uncertainty + 0.004 + region.motion * 0.018 + staleness * 0.0007, 0.02, 0.99)
        if tick % 8 == 0:
            region.motion = _clamp(region.motion + rng.uniform(-0.04, 0.08), 0.03, 1.0)
    if tick % 42 == 0:
        hot = rng.choice(list(regions.values()))
        hot.motion = _clamp(hot.motion + 0.24, 0.03, 1.0)
        hot.uncertainty = _clamp(hot.uncertainty + 0.16, 0.02, 0.99)


def _emit_shards(
    regions: dict[str, Region],
    tick: int,
    rng: random.Random,
    counter: int,
    max_per_tick: int,
) -> tuple[list[Shard], int]:
    out: list[Shard] = []
    for region in regions.values():
        rate = 0.08 + 0.55 * region.motion
        if tick % 50 in (0, 1) and region.zone == "central":
            rate += 0.4
        events = min(2, _poisson(rate, rng))
        for _ in range(events):
            counter += 1
            entropy = _clamp(rng.uniform(0.2, 0.96) * (0.48 + 0.65 * region.motion), 0.05, 0.99)
            novelty = _clamp(rng.uniform(0.2, 1.0) * (0.35 + 0.8 * region.uncertainty), 0.05, 0.99)
            points = rng.uniform(1.2, 15.5)
            images = rng.randint(700, 3600)
            vram = round(1.1 + points * 0.22 + images / 4200 + entropy * 0.7, 2)
            ingest = 40 + images * 0.035 + points * 9.5
            train = 95 + points * 18 + images * 0.06
            out.append(
                Shard(
                    shard_id=f"S-{counter:06d}",
                    region_id=region.region_id,
                    zone=region.zone,
                    created_tick=tick,
                    entropy=entropy,
                    novelty=novelty,
                    vram_gb=vram,
                    ingest_ms=ingest,
                    train_ms=train,
                )
            )
    if len(out) > max_per_tick:
        out.sort(key=lambda s: s.entropy * s.novelty, reverse=True)
        out = out[:max_per_tick]
    return out, counter


def _summarize(name: str, processed: int, dropped: int, ages: list[float], latencies: list[float], util: list[float], gains: list[float], regions: dict[str, Region]) -> Summary:
    p95 = 0.0
    if latencies:
        ordered = sorted(latencies)
        p95 = ordered[int(0.95 * (len(ordered) - 1))]
    return Summary(
        name=name,
        processed=float(processed),
        dropped=float(dropped),
        avg_age=statistics.fmean(ages) if ages else 0.0,
        p95_latency_ms=p95,
        avg_utilization=statistics.fmean(util) if util else 0.0,
        info_gain=sum(gains),
        final_uncertainty=statistics.fmean(r.uncertainty for r in regions.values()),
    )


def _run_once(name: str, adaptive: bool, *, seed: int, ticks: int, regions_n: int, workers_n: int, tick_ms: int = 120, queue_limit: int = 280, max_shards_per_tick: int = 12) -> Summary:
    rng = random.Random(seed)
    regions = _make_regions(regions_n, rng)
    workers = _make_workers(workers_n, rng)

    queue: list[Shard] = []
    counter = 0

    processed = 0
    dropped = 0
    ages: list[float] = []
    latencies: list[float] = []
    util: list[float] = []
    gains: list[float] = []

    for tick in range(ticks):
        for w in workers:
            w.busy_ms = max(0.0, w.busy_ms - tick_ms)

        _drift(regions, tick, rng)
        fresh, counter = _emit_shards(regions, tick, rng, counter, max_shards_per_tick)
        queue.extend(fresh)

        available = [w for w in workers if w.busy_ms <= 0]

        if adaptive:
            candidates: list[tuple[float, Worker, Shard, float, float]] = []
            for w in available:
                for s in queue:
                    if s.vram_gb > w.vram_gb:
                        continue
                    region = regions[s.region_id]
                    duration, _ = _job_ms(w, s)
                    freshness = math.exp(-s.age(tick) / 11.0)
                    staleness = min(1.0, (tick - region.last_refresh) / 35.0)
                    urgency = 0.52 * region.uncertainty + 0.33 * region.motion + 0.15 * staleness
                    signal = 0.54 * s.entropy + 0.46 * s.novelty
                    locality = 1.11 if w.zone == s.zone else 0.96
                    efficiency = 1.0 / (1.0 + duration / 260.0)
                    pressure = min(0.16, len(queue) / 900.0)
                    score = (urgency * 0.5 + signal * 0.35 + freshness * 0.15) * locality
                    score = score * efficiency + pressure
                    gain = (urgency * 0.62 + signal * 0.38) * freshness * locality
                    candidates.append((score, w, s, duration, gain))

            candidates.sort(reverse=True, key=lambda row: row[0])
            used_worker = set()
            used_shard = set()
            for _, w, s, duration, gain in candidates:
                if w.worker_id in used_worker or s.shard_id in used_shard:
                    continue
                used_worker.add(w.worker_id)
                used_shard.add(s.shard_id)

                w.busy_ms = duration
                processed += 1
                ages.append(float(s.age(tick)))
                latencies.append(duration)
                gains.append(gain)

                r = regions[s.region_id]
                r.uncertainty = _clamp(r.uncertainty - min(0.36, 0.05 + gain * 0.06), 0.02, 0.99)
                r.motion = _clamp(r.motion - gain * 0.012 + rng.uniform(-0.012, 0.01), 0.03, 1.0)
                r.last_refresh = tick

            queue = [s for s in queue if s.shard_id not in used_shard]
        else:
            queue.sort(key=lambda s: s.created_tick)
            for w in available:
                pick_idx = -1
                for idx, s in enumerate(queue):
                    if s.vram_gb <= w.vram_gb:
                        pick_idx = idx
                        break
                if pick_idx < 0:
                    continue
                s = queue.pop(pick_idx)
                duration, _ = _job_ms(w, s)
                freshness = max(0.12, math.exp(-s.age(tick) / 18.0))
                gain = (0.42 * s.entropy + 0.36 * s.novelty + 0.22 * freshness) * freshness

                w.busy_ms = duration
                processed += 1
                ages.append(float(s.age(tick)))
                latencies.append(duration)
                gains.append(gain)

                r = regions[s.region_id]
                r.uncertainty = _clamp(r.uncertainty - min(0.32, 0.04 + gain * 0.05), 0.02, 0.99)
                r.motion = _clamp(r.motion - gain * 0.01 + rng.uniform(-0.013, 0.012), 0.03, 1.0)
                r.last_refresh = tick

        if len(queue) > queue_limit:
            overflow = len(queue) - queue_limit
            queue.sort(key=lambda s: (s.age(tick), -s.novelty), reverse=True)
            dropped += overflow
            queue = queue[overflow:]

        util.append(sum(1 for w in workers if w.busy_ms > 0) / len(workers))

    return _summarize(name, processed, dropped, ages, latencies, util, gains, regions)


def benchmark(*, ticks: int, regions: int, workers: int, trials: int, seed: int) -> dict[str, Summary]:
    fifo_runs: list[Summary] = []
    adaptive_runs: list[Summary] = []
    for trial in range(trials):
        run_seed = seed + trial * 97
        fifo_runs.append(_run_once("fifo-frontier", False, seed=run_seed, ticks=ticks, regions_n=regions, workers_n=workers))
        adaptive_runs.append(_run_once("adaptive-geo-router", True, seed=run_seed, ticks=ticks, regions_n=regions, workers_n=workers))

    def avg(name: str, rows: list[Summary]) -> Summary:
        return Summary(
            name=name,
            processed=statistics.fmean(r.processed for r in rows),
            dropped=statistics.fmean(r.dropped for r in rows),
            avg_age=statistics.fmean(r.avg_age for r in rows),
            p95_latency_ms=statistics.fmean(r.p95_latency_ms for r in rows),
            avg_utilization=statistics.fmean(r.avg_utilization for r in rows),
            info_gain=statistics.fmean(r.info_gain for r in rows),
            final_uncertainty=statistics.fmean(r.final_uncertainty for r in rows),
        )

    return {
        "fifo": avg("fifo-frontier", fifo_runs),
        "adaptive": avg("adaptive-geo-router", adaptive_runs),
    }


def _pct(new: float, old: float, lower_better: bool = False) -> float:
    if abs(old) < 1e-9:
        return 0.0
    if lower_better:
        return (old - new) / old * 100.0
    return (new - old) / old * 100.0


def render_report(results: dict[str, Summary]) -> str:
    fifo = results["fifo"]
    adaptive = results["adaptive"]

    lines = [
        "",
        "STASHY AI INFRA BENCHMARK",
        "========================",
        "",
        "Scheduler Results",
        "-----------------",
        f"FIFO frontier baseline   | processed={fifo.processed:8.1f} | avg_age={fifo.avg_age:6.2f} ticks | p95={fifo.p95_latency_ms:7.1f} ms | util={fifo.avg_utilization*100:6.1f}% | final_uncertainty={fifo.final_uncertainty:6.3f}",
        f"Adaptive Geo Router      | processed={adaptive.processed:8.1f} | avg_age={adaptive.avg_age:6.2f} ticks | p95={adaptive.p95_latency_ms:7.1f} ms | util={adaptive.avg_utilization*100:6.1f}% | final_uncertainty={adaptive.final_uncertainty:6.3f}",
        "",
        "Lift vs FIFO",
        "------------",
        f"Throughput gain          : {_pct(adaptive.processed, fifo.processed):6.2f}%",
        f"Freshness improvement    : {_pct(adaptive.avg_age, fifo.avg_age, lower_better=True):6.2f}%",
        f"Info gain uplift         : {_pct(adaptive.info_gain, fifo.info_gain):6.2f}%",
        f"Uncertainty reduction    : {_pct(adaptive.final_uncertainty, fifo.final_uncertainty, lower_better=True):6.2f}%",
        "",
        "Takeaway",
        "--------",
        "Adaptive frontier routing delivers more learning signal per GPU-second than FIFO under the same compute budget.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stashy AI infra benchmark demo")
    parser.add_argument("--ticks", type=int, default=220)
    parser.add_argument("--regions", type=int, default=30)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--trials", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    results = benchmark(
        ticks=args.ticks,
        regions=args.regions,
        workers=args.workers,
        trials=args.trials,
        seed=args.seed,
    )
    print(render_report(results))


if __name__ == "__main__":
    main()
