"""Day 6. Monte Carlo over CVP inputs.

Treat each input as a triangular distribution centred on its base value with
+/- span on each side. Run N trials, compute BE for each, return a small
histogram + percentile summary.

Pure Python (random module). Seeded for determinism. ~50ms for 5000 runs.
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from cvp_schema import CVPInputs


@dataclass
class MonteCarloResult:
    n_runs: int
    span_pct: float                    # +/- range applied to each input
    seed: int
    median_be: float
    p5_be: float
    p95_be: float
    p25_be: float
    p75_be: float
    mean_be: float
    stdev_be: float
    pct_undefined: float               # fraction of trials with cm <= 0
    histogram: list[dict]              # [{"bin_lo","bin_hi","count","pct"}, ...]
    bin_count: int


def simulate(inputs: CVPInputs, *,
             n_runs: int = 4000,
             span_pct: float = 0.20,
             seed: int = 42,
             bin_count: int = 24) -> MonteCarloResult:
    """Triangular shocks on price, vc, fixed within +/- span, returns
    histogram + percentile summary of BE units."""
    if n_runs < 100:
        n_runs = 100
    if span_pct <= 0:
        span_pct = 0.05
    rng = random.Random(seed)
    p0 = inputs.price_per_unit
    v0 = inputs.variable_cost_per_unit
    f0 = inputs.fixed_cost
    bes: list[float] = []
    undefined = 0
    for _ in range(n_runs):
        # Triangular(low, high, mode=base) keeps the centre likely
        p = rng.triangular(p0 * (1 - span_pct), p0 * (1 + span_pct), p0)
        v = rng.triangular(v0 * (1 - span_pct), v0 * (1 + span_pct), v0)
        f = rng.triangular(f0 * (1 - span_pct), f0 * (1 + span_pct), f0)
        cm = p - v
        if cm <= 0:
            undefined += 1
            continue
        bes.append(f / cm)

    pct_undefined = undefined / n_runs

    if not bes:
        return MonteCarloResult(
            n_runs=n_runs, span_pct=span_pct, seed=seed,
            median_be=float("nan"), p5_be=float("nan"), p95_be=float("nan"),
            p25_be=float("nan"), p75_be=float("nan"),
            mean_be=float("nan"), stdev_be=float("nan"),
            pct_undefined=pct_undefined, histogram=[], bin_count=0,
        )

    bes.sort()
    median = statistics.median(bes)
    mean = statistics.fmean(bes)
    stdev = statistics.pstdev(bes) if len(bes) > 1 else 0.0
    p5 = _percentile(bes, 5)
    p25 = _percentile(bes, 25)
    p75 = _percentile(bes, 75)
    p95 = _percentile(bes, 95)
    histogram = _histogram(bes, bin_count)
    return MonteCarloResult(
        n_runs=n_runs, span_pct=span_pct, seed=seed,
        median_be=median, p5_be=p5, p95_be=p95,
        p25_be=p25, p75_be=p75,
        mean_be=mean, stdev_be=stdev,
        pct_undefined=pct_undefined,
        histogram=histogram, bin_count=bin_count,
    )


def _percentile(sorted_xs: list[float], q: float) -> float:
    """q in 0-100. Linear interpolation between the two nearest ranks."""
    if not sorted_xs:
        return float("nan")
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    pos = (q / 100.0) * (len(sorted_xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_xs) - 1)
    frac = pos - lo
    return sorted_xs[lo] * (1 - frac) + sorted_xs[hi] * frac


def _histogram(sorted_xs: list[float], bin_count: int) -> list[dict]:
    """Return bins as [{"bin_lo","bin_hi","count","pct"}, ...]. Skip empty bins
    only at the tails. Trim outliers above 99.5th percentile so the chart
    stays readable on long-tailed distributions.
    """
    if not sorted_xs or bin_count <= 0:
        return []
    cap = _percentile(sorted_xs, 99.5)
    floor = sorted_xs[0]
    if cap <= floor:
        cap = sorted_xs[-1]
    width = (cap - floor) / bin_count if cap > floor else 1.0
    counts = [0] * bin_count
    for x in sorted_xs:
        if x < floor:
            continue
        if x >= cap:
            counts[bin_count - 1] += 1
            continue
        b = int((x - floor) / width)
        if 0 <= b < bin_count:
            counts[b] += 1
    total = sum(counts)
    out = []
    for i, c in enumerate(counts):
        out.append({
            "bin_lo": floor + i * width,
            "bin_hi": floor + (i + 1) * width,
            "count": c,
            "pct": (c / total) if total else 0.0,
        })
    return out
