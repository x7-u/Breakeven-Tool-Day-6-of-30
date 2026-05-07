"""Day 6. Pipeline + sample workbook integration tests (skip_ai mode)."""
from __future__ import annotations

from pathlib import Path

import pytest
from pipeline import analyse, to_dict

HERE = Path(__file__).resolve().parent
SAMPLE_DIR = HERE.parent / "sample_data"

SAMPLES = [
    "sample_coffee_shop.xlsx",
    "sample_low_cost_airline.xlsx",
    "sample_software_saas.xlsx",
]


@pytest.mark.parametrize("fname", SAMPLES)
def test_each_sample_round_trips(fname):
    path = SAMPLE_DIR / fname
    if not path.exists():
        pytest.skip(f"sample missing: {fname}")
    res = analyse(path=path, source_filename=fname, skip_ai=True)
    assert res.cvp.headline.contribution_margin_per_unit > 0
    assert res.cvp.headline.break_even_units > 0
    # 3 variables x 5 deltas = 15 sensitivity rows
    assert len(res.cvp.sensitivity) == 15
    # Tornado entry per variable
    assert len(res.cvp.tornado) == 3
    # to_dict should be JSON-serialisable
    import json
    json.dumps(to_dict(res))


def test_skip_ai_does_not_call_provider():
    path = SAMPLE_DIR / "sample_coffee_shop.xlsx"
    if not path.exists():
        pytest.skip("sample missing")
    res = analyse(path=path, source_filename=path.name, skip_ai=True)
    assert res.commentary.skipped is True
    assert res.commentary.cost_usd == 0.0
    assert res.total_cost_usd == 0.0


def test_target_profit_units_present_when_target_provided():
    path = SAMPLE_DIR / "sample_software_saas.xlsx"
    if not path.exists():
        pytest.skip("sample missing")
    res = analyse(path=path, source_filename=path.name, skip_ai=True)
    assert res.cvp.headline.target_profit_units is not None
