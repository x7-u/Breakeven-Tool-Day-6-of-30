"""Day 6. Tests for cvp_maths."""
from __future__ import annotations

import math

from cvp_maths import (
    SENSITIVITY_DELTAS,
    SENSITIVITY_VARIABLES,
    headline_stats,
    operating_leverage_at,
    sensitivity_table,
    tornado,
)
from cvp_schema import CVPInputs, CVPMetadata


def _md(current_volume=None) -> CVPMetadata:
    return CVPMetadata("Acme", "GBP", "2026-Q2", current_volume)


def _inp(fixed=1000, vc=2.0, price=5.0, target=None) -> CVPInputs:
    return CVPInputs(
        fixed_cost=fixed,
        variable_cost_per_unit=vc,
        price_per_unit=price,
        target_profit=target,
    )


def test_break_even_basic():
    h = headline_stats(_inp(), _md())
    # 1000 / (5 - 2) = 333.333
    assert math.isclose(h.contribution_margin_per_unit, 3.0)
    assert math.isclose(h.cm_ratio, 3.0 / 5.0)
    assert math.isclose(h.break_even_units, 1000 / 3, rel_tol=1e-6)
    assert math.isclose(h.break_even_revenue, (1000 / 3) * 5.0, rel_tol=1e-6)


def test_break_even_with_target_profit():
    h = headline_stats(_inp(target=600), _md())
    assert math.isclose(h.target_profit_units, (1000 + 600) / 3.0, rel_tol=1e-6)
    assert h.target_profit_revenue is not None


def test_margin_of_safety_when_above_be():
    h = headline_stats(_inp(), _md(current_volume=500))
    # BE = 333.33 so MoS = 500 - 333.33 = 166.67
    assert h.margin_of_safety_units is not None
    assert h.margin_of_safety_units > 0
    assert h.margin_of_safety_pct is not None
    assert 0 < h.margin_of_safety_pct < 1


def test_margin_of_safety_negative_below_be():
    h = headline_stats(_inp(), _md(current_volume=200))
    assert h.margin_of_safety_units is not None
    assert h.margin_of_safety_units < 0


def test_operating_leverage_positive_only_above_be():
    # Below BE: profit <= 0, leverage None
    assert operating_leverage_at(_inp(), 200) is None
    # At BE: profit = 0, leverage None
    assert operating_leverage_at(_inp(), 1000 / 3) is None
    # Above BE: defined
    lev = operating_leverage_at(_inp(), 500)
    assert lev is not None and lev > 0


def test_break_even_is_inf_when_cm_zero_or_negative():
    # CM = 0 path is covered at the schema level (raises). Test maths directly:
    # use a manually-constructed input bypassing schema sanity.
    bad = CVPInputs(fixed_cost=1000, variable_cost_per_unit=10, price_per_unit=8)
    h = headline_stats(bad, _md())
    assert h.break_even_units == float("inf")
    assert h.break_even_revenue == float("inf")


def test_sensitivity_table_shape():
    rows = sensitivity_table(_inp())
    assert len(rows) == len(SENSITIVITY_VARIABLES) * len(SENSITIVITY_DELTAS)
    # The 0% delta row for each variable should equal the baseline BE.
    base = headline_stats(_inp(), _md()).break_even_units
    zeros = [r for r in rows if r.delta_pct == 0.0]
    assert len(zeros) == 3
    for r in zeros:
        assert r.new_break_even_units is not None
        assert math.isclose(r.new_break_even_units, base, rel_tol=1e-6)
        assert r.swing_units == 0.0


def test_sensitivity_negative_when_price_drops():
    # Lower price -> CM shrinks -> BE rises -> swing positive.
    rows = sensitivity_table(_inp())
    minus = [r for r in rows
             if r.variable == "price_per_unit" and r.delta_pct == -0.10][0]
    assert minus.swing_units is not None and minus.swing_units > 0


def test_sensitivity_handles_cm_collapse():
    # With price = 5, vc = 2, a -100% price shock takes CM negative.
    # Our delta set only goes to -20%; just sanity-check that the row exists.
    rows = sensitivity_table(_inp(price=2.5))
    minus20 = [r for r in rows
               if r.variable == "price_per_unit" and r.delta_pct == -0.20][0]
    # New price = 2.0, equal to vc -> CM = 0 -> BE undefined.
    assert minus20.new_break_even_units is None


def test_tornado_sorted_by_abs_max():
    rows = sensitivity_table(_inp())
    t = tornado(rows)
    assert len(t) == 3
    for i in range(len(t) - 1):
        assert t[i].abs_max_swing >= t[i + 1].abs_max_swing
