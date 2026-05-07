"""Day 6. Industry CM-ratio benchmarks.

Hand-curated typical contribution-margin ranges by industry. Sources are
trade-press medians and broker comp tables (rough, directional, not audited).
The UI uses these to overlay a peer band on the user's CM ratio.

Add new industries to the dict; UI auto-picks them up.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IndustryBenchmark:
    industry: str
    cm_ratio_low: float
    cm_ratio_high: float
    operating_leverage_typical: float | None = None
    note: str = ""


INDUSTRY_BENCHMARKS: dict[str, IndustryBenchmark] = {
    "coffee shop":         IndustryBenchmark("Coffee shop / cafe", 0.62, 0.72, 4.5,
        "Volume is the lever; rent + labour dominate fixed."),
    "cafe":                IndustryBenchmark("Coffee shop / cafe", 0.62, 0.72, 4.5, ""),
    "restaurant":          IndustryBenchmark("Restaurant", 0.55, 0.68, 5.0,
        "Food cost ~30%, labour ~30%, rent ~10%."),
    "saas":                IndustryBenchmark("Software / SaaS", 0.75, 0.92, 8.0,
        "High fixed (eng + sales), near-zero per-seat marginal cost."),
    "software":            IndustryBenchmark("Software / SaaS", 0.75, 0.92, 8.0, ""),
    "ecommerce":           IndustryBenchmark("E-commerce / DTC", 0.30, 0.55, 3.0,
        "Heavy COGS + fulfilment; CM compressed by paid acquisition."),
    "dtc":                 IndustryBenchmark("E-commerce / DTC", 0.30, 0.55, 3.0, ""),
    "consultancy":         IndustryBenchmark("Consultancy / services", 0.50, 0.75, 3.5,
        "People are the variable cost; utilisation is everything."),
    "services":            IndustryBenchmark("Consultancy / services", 0.50, 0.75, 3.5, ""),
    "manufacturing":       IndustryBenchmark("Manufacturing", 0.20, 0.40, 4.0,
        "Materials + direct labour eat the CM; fixed overhead split widely."),
    "airline":             IndustryBenchmark("Airline / transport", 0.18, 0.30, 12.0,
        "Fuel + handling per seat; massive fleet/slot fixed cost."),
    "transport":           IndustryBenchmark("Airline / transport", 0.18, 0.30, 12.0, ""),
    "retail":              IndustryBenchmark("Retail apparel", 0.45, 0.60, 3.5,
        "COGS ~40-55%; rent + staff dominate fixed."),
    "retail apparel":      IndustryBenchmark("Retail apparel", 0.45, 0.60, 3.5, ""),
    "subscription":        IndustryBenchmark("Subscription box", 0.35, 0.55, 4.0,
        "Per-shipment COGS + fulfilment; churn turns CM into a leaky bucket."),
    "construction":        IndustryBenchmark("Construction", 0.15, 0.30, 3.0,
        "Materials + sub-contractors per project; site overhead is fixed."),
}


def lookup(industry: str | None) -> IndustryBenchmark | None:
    if not industry:
        return None
    key = industry.strip().lower()
    if key in INDUSTRY_BENCHMARKS:
        return INDUSTRY_BENCHMARKS[key]
    # Loose substring match
    for k, v in INDUSTRY_BENCHMARKS.items():
        if k in key or key in k:
            return v
    return None


def all_industries() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in INDUSTRY_BENCHMARKS.values():
        if v.industry not in seen:
            seen.add(v.industry)
            out.append(v.industry)
    return sorted(out)
