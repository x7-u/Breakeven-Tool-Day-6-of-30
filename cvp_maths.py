"""Day 6. Pure CVP maths.

Inputs from cvp_schema.CVPInputs. Outputs:
  - HeadlineStats: BE units / revenue, CM per unit + ratio, MoS, target volume,
    cash BE, capacity reachability.
  - SensitivityRow: per-variable per-delta new BE point + change vs baseline.
  - MultiProductStats: weighted CM + blended BE for product mixes.
  - StepCostBE: BE within each fixed-cost segment of a step ladder.
  - heatmap_grid: 2D BE matrix for price vs vc combinations.
  - operating_leverage_at(volume): leverage scalar at a given volume level.

No IO, no AI calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cvp_schema import CVPInputs, CVPMetadata, Product, StepCost, VolumePoint

SENSITIVITY_DELTAS = (-0.20, -0.10, 0.0, 0.10, 0.20)
SENSITIVITY_VARIABLES = ("price_per_unit", "variable_cost_per_unit", "fixed_cost")


@dataclass
class HeadlineStats:
    contribution_margin_per_unit: float
    cm_ratio: float
    break_even_units: float
    break_even_revenue: float
    margin_of_safety_units: float | None = None
    margin_of_safety_pct: float | None = None
    target_profit_units: float | None = None
    target_profit_revenue: float | None = None
    operating_leverage_at_current: float | None = None
    cash_break_even_units: float | None = None        # excludes non-cash fixed
    capacity_units: float | None = None
    capacity_reachable: bool | None = None            # BE <= capacity?
    capacity_buffer_pct: float | None = None          # (capacity - BE) / capacity
    covenant_min_revenue: float | None = None         # bank covenant
    covenant_breach: bool | None = None               # BE rev > covenant min?
    covenant_buffer_pct: float | None = None          # (current rev - covenant) / covenant


@dataclass
class SensitivityRow:
    variable: str
    delta_pct: float
    new_value: float
    new_break_even_units: float | None
    swing_units: float | None
    swing_pct: float | None


@dataclass
class TornadoEntry:
    variable: str
    swing_minus_10_pct: float
    swing_plus_10_pct: float
    abs_max_swing: float


@dataclass
class MultiProductStats:
    """Weighted-average CM and blended BE across a product mix.

    Each product's mix_pct is treated as the share of total *units* sold.
    """
    weighted_price: float
    weighted_variable_cost: float
    weighted_cm_per_unit: float
    weighted_cm_ratio: float
    blended_break_even_units: float
    blended_break_even_revenue: float
    per_product: list[dict] = field(default_factory=list)
    # per_product entries: {name, price, vc, mix_pct, cm_per_unit, cm_ratio,
    #                       allocated_units, allocated_revenue}


@dataclass
class StepCostBE:
    """A BE point within one segment of a step-cost ladder.

    Segments are ordered by ascending threshold. Segment 0 is the baseline
    (no extra fixed). Segment k's fixed = base + sum(extra_fixed_cost for
    steps[:k]).
    """
    segment: int
    fixed_cost_at_segment: float
    units_lower: float          # inclusive lower bound for this segment
    units_upper: float | None   # exclusive upper bound; None for the last
    break_even_units: float | None
    is_reachable_in_segment: bool


@dataclass
class CVPResult:
    metadata: CVPMetadata
    inputs: CVPInputs
    headline: HeadlineStats
    sensitivity: list[SensitivityRow] = field(default_factory=list)
    tornado: list[TornadoEntry] = field(default_factory=list)
    multi_product: MultiProductStats | None = None
    step_cost_be: list[StepCostBE] = field(default_factory=list)
    time_phased: list[TimePhasedPoint] = field(default_factory=list)


# ---- Headline ------------------------------------------------------

def headline_stats(inputs: CVPInputs, metadata: CVPMetadata) -> HeadlineStats:
    cm = inputs.price_per_unit - inputs.variable_cost_per_unit
    cm_ratio = cm / inputs.price_per_unit if inputs.price_per_unit > 0 else 0.0
    be_units = inputs.fixed_cost / cm if cm > 0 else float("inf")
    be_revenue = be_units * inputs.price_per_unit if cm > 0 else float("inf")

    h = HeadlineStats(
        contribution_margin_per_unit=cm,
        cm_ratio=cm_ratio,
        break_even_units=be_units,
        break_even_revenue=be_revenue,
    )

    if inputs.target_profit is not None and cm > 0:
        h.target_profit_units = (inputs.fixed_cost + inputs.target_profit) / cm
        h.target_profit_revenue = h.target_profit_units * inputs.price_per_unit

    if metadata.current_volume is not None and cm > 0:
        mos = metadata.current_volume - be_units
        h.margin_of_safety_units = mos
        if metadata.current_volume > 0:
            h.margin_of_safety_pct = mos / metadata.current_volume
        contribution = metadata.current_volume * cm
        profit = contribution - inputs.fixed_cost
        if profit > 0:
            h.operating_leverage_at_current = contribution / profit

    if metadata.non_cash_amount is not None and cm > 0:
        cash_fixed = max(0.0, inputs.fixed_cost - metadata.non_cash_amount)
        h.cash_break_even_units = cash_fixed / cm

    if metadata.capacity_units is not None:
        h.capacity_units = metadata.capacity_units
        if metadata.capacity_units > 0 and cm > 0:
            h.capacity_reachable = be_units <= metadata.capacity_units
            h.capacity_buffer_pct = (metadata.capacity_units - be_units) / metadata.capacity_units
        else:
            h.capacity_reachable = False
            h.capacity_buffer_pct = -1.0

    if metadata.covenant_min_revenue is not None:
        h.covenant_min_revenue = metadata.covenant_min_revenue
        if cm > 0 and metadata.current_volume is not None:
            current_revenue = metadata.current_volume * inputs.price_per_unit
            h.covenant_breach = current_revenue < metadata.covenant_min_revenue
            if metadata.covenant_min_revenue > 0:
                h.covenant_buffer_pct = (current_revenue - metadata.covenant_min_revenue) / metadata.covenant_min_revenue
        elif cm > 0:
            # No current_volume; compare BE revenue to covenant
            h.covenant_breach = be_revenue < metadata.covenant_min_revenue

    return h


# ---- Time-phased BE ----------------------------------------------

@dataclass
class TimePhasedPoint:
    """Per-period BE projection.

    cumulative_units = sum of planned volume up to and including this period.
    cumulative_profit = cum_units * cm - fixed (assuming fixed is per-period;
    multiplied by period count).
    crossed = first period where cumulative_profit >= 0.
    """
    period_label: str
    units: float
    cumulative_units: float
    cumulative_profit: float
    crossed: bool


def time_phased_be(inputs: CVPInputs, curve: list[VolumePoint]) -> list[TimePhasedPoint]:
    """Walk a planned volume curve, accumulate units, and report when the
    business crosses cumulative break-even (cumulative profit >= 0).

    Note: fixed cost is treated as recurring (per period). Cumulative fixed
    is fixed * period_index.
    """
    if not curve:
        return []
    cm = inputs.price_per_unit - inputs.variable_cost_per_unit
    out: list[TimePhasedPoint] = []
    cum_units = 0.0
    crossed = False
    for i, point in enumerate(curve, start=1):
        cum_units += point.units
        if cm <= 0:
            cum_profit = -inputs.fixed_cost * i
        else:
            cum_profit = cum_units * cm - inputs.fixed_cost * i
        cross_now = (not crossed) and cum_profit >= 0
        if cross_now:
            crossed = True
        out.append(TimePhasedPoint(
            period_label=point.period_label,
            units=point.units,
            cumulative_units=cum_units,
            cumulative_profit=cum_profit,
            crossed=cross_now,
        ))
    return out


def first_crossing_period(rows: list[TimePhasedPoint]) -> str | None:
    for r in rows:
        if r.crossed:
            return r.period_label
    return None


# ---- Sensitivity ---------------------------------------------------

def sensitivity_table(inputs: CVPInputs) -> list[SensitivityRow]:
    base = headline_stats(inputs, CVPMetadata("", "", "", None)).break_even_units
    out: list[SensitivityRow] = []
    for var in SENSITIVITY_VARIABLES:
        baseline_value = getattr(inputs, var)
        for d in SENSITIVITY_DELTAS:
            shocked = _shock(inputs, var, d)
            new_be = _safe_be(shocked)
            swing_units: float | None
            swing_pct: float | None
            if new_be is None or base == 0 or base == float("inf"):
                swing_units = None
                swing_pct = None
            else:
                swing_units = new_be - base
                swing_pct = swing_units / base if base != 0 else None
            out.append(SensitivityRow(
                variable=var,
                delta_pct=d,
                new_value=baseline_value * (1 + d),
                new_break_even_units=new_be,
                swing_units=swing_units,
                swing_pct=swing_pct,
            ))
    return out


def tornado(sens: list[SensitivityRow]) -> list[TornadoEntry]:
    by_var: dict[str, dict[float, float]] = {}
    for r in sens:
        if r.swing_units is None or r.delta_pct == 0.0:
            continue
        by_var.setdefault(r.variable, {})[r.delta_pct] = r.swing_units
    out: list[TornadoEntry] = []
    for var, deltas in by_var.items():
        m = deltas.get(-0.10, 0.0)
        p = deltas.get(0.10, 0.0)
        out.append(TornadoEntry(
            variable=var,
            swing_minus_10_pct=m,
            swing_plus_10_pct=p,
            abs_max_swing=max(abs(m), abs(p)),
        ))
    out.sort(key=lambda t: t.abs_max_swing, reverse=True)
    return out


def operating_leverage_at(inputs: CVPInputs, volume: float) -> float | None:
    cm = inputs.price_per_unit - inputs.variable_cost_per_unit
    if cm <= 0:
        return None
    contribution = cm * volume
    profit = contribution - inputs.fixed_cost
    if profit <= 0:
        return None
    return contribution / profit


# ---- Multi-product -------------------------------------------------

def multi_product_stats(products: list[Product], fixed_cost: float) -> MultiProductStats | None:
    """Weighted-average CM treating mix_pct as share of total units.

    blended_BE_units = fixed / weighted_cm_per_unit
    Per-product allocated units = blended_BE * mix_pct.
    """
    if not products:
        return None
    weighted_price = sum(p.price_per_unit * p.mix_pct for p in products)
    weighted_vc = sum(p.variable_cost_per_unit * p.mix_pct for p in products)
    weighted_cm = weighted_price - weighted_vc
    weighted_cm_ratio = weighted_cm / weighted_price if weighted_price > 0 else 0.0
    if weighted_cm > 0:
        blended_be = fixed_cost / weighted_cm
        blended_be_rev = blended_be * weighted_price
    else:
        blended_be = float("inf")
        blended_be_rev = float("inf")
    per_product = []
    for p in products:
        cm = p.price_per_unit - p.variable_cost_per_unit
        ratio = cm / p.price_per_unit if p.price_per_unit > 0 else 0.0
        alloc_units = (blended_be * p.mix_pct) if blended_be != float("inf") else float("inf")
        alloc_rev = alloc_units * p.price_per_unit if alloc_units != float("inf") else float("inf")
        per_product.append({
            "name": p.name,
            "price": p.price_per_unit,
            "vc": p.variable_cost_per_unit,
            "mix_pct": p.mix_pct,
            "cm_per_unit": cm,
            "cm_ratio": ratio,
            "allocated_units": alloc_units,
            "allocated_revenue": alloc_rev,
        })
    return MultiProductStats(
        weighted_price=weighted_price,
        weighted_variable_cost=weighted_vc,
        weighted_cm_per_unit=weighted_cm,
        weighted_cm_ratio=weighted_cm_ratio,
        blended_break_even_units=blended_be,
        blended_break_even_revenue=blended_be_rev,
        per_product=per_product,
    )


# ---- Step-cost ladder ---------------------------------------------

def step_cost_be(inputs: CVPInputs, steps: list[StepCost]) -> list[StepCostBE]:
    """Compute BE in each fixed-cost segment of the step ladder.

    Segment 0: fixed = base; range 0 to first step (or +inf if no steps).
    Segment k: fixed = base + sum(extra for steps[:k]); range steps[k-1] to steps[k].
    A segment's BE is "reachable in segment" if BE falls within the segment range.
    """
    cm = inputs.price_per_unit - inputs.variable_cost_per_unit
    if cm <= 0 or not steps:
        # Fallback: just one segment with the baseline fixed
        be = inputs.fixed_cost / cm if cm > 0 else None
        return [StepCostBE(
            segment=0,
            fixed_cost_at_segment=inputs.fixed_cost,
            units_lower=0.0,
            units_upper=None,
            break_even_units=be,
            is_reachable_in_segment=be is not None,
        )]
    # Build segment boundaries
    boundaries = [0.0] + [s.above_units for s in steps] + [None]
    fixed_running = inputs.fixed_cost
    out: list[StepCostBE] = []
    for k in range(len(steps) + 1):
        if k > 0:
            fixed_running += steps[k - 1].extra_fixed_cost
        lower = boundaries[k]
        upper = boundaries[k + 1]
        be = fixed_running / cm if cm > 0 else None
        reachable = be is not None and lower <= be and (upper is None or be < upper)
        out.append(StepCostBE(
            segment=k,
            fixed_cost_at_segment=fixed_running,
            units_lower=lower or 0.0,
            units_upper=upper,
            break_even_units=be,
            is_reachable_in_segment=reachable,
        ))
    return out


def first_reachable_step_be(steps: list[StepCostBE]) -> float | None:
    for s in steps:
        if s.is_reachable_in_segment and s.break_even_units is not None:
            return s.break_even_units
    return None


# ---- 2D heatmap (price vs vc) -------------------------------------

def heatmap_grid(inputs: CVPInputs, *, n: int = 9, span: float = 0.20) -> dict:
    """Return a 2D grid of BE units across +/-span on price (rows) and vc (cols).

    Returns: {price_axis: [...], vc_axis: [...], be_grid: [[...],[...],...]}.
    Used by the UI to render a heatmap. n should be odd so 0% delta sits centred.
    """
    if n < 3:
        n = 3
    if n % 2 == 0:
        n += 1
    step = (2 * span) / (n - 1)
    deltas = [-span + i * step for i in range(n)]
    price_axis = [inputs.price_per_unit * (1 + d) for d in deltas]
    vc_axis = [inputs.variable_cost_per_unit * (1 + d) for d in deltas]
    grid: list[list[float | None]] = []
    for p in price_axis:
        row: list[float | None] = []
        for vc in vc_axis:
            cm = p - vc
            if cm <= 0:
                row.append(None)
            else:
                row.append(inputs.fixed_cost / cm)
        grid.append(row)
    return {
        "price_axis": price_axis,
        "vc_axis": vc_axis,
        "deltas": deltas,
        "be_grid": grid,
    }


# ---- helpers -------------------------------------------------------

def _shock(inputs: CVPInputs, variable: str, delta: float) -> CVPInputs:
    base = getattr(inputs, variable)
    new_value = base * (1 + delta)
    kwargs = {
        "fixed_cost": inputs.fixed_cost,
        "variable_cost_per_unit": inputs.variable_cost_per_unit,
        "price_per_unit": inputs.price_per_unit,
        "target_profit": inputs.target_profit,
    }
    kwargs[variable] = new_value
    return CVPInputs(**kwargs)


def _safe_be(inputs: CVPInputs) -> float | None:
    cm = inputs.price_per_unit - inputs.variable_cost_per_unit
    if cm <= 0:
        return None
    return inputs.fixed_cost / cm
