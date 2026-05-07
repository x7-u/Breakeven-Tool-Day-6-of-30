"""Day 6 test isolation. Mirrors the Day 5 pattern."""
from __future__ import annotations

import sys
from pathlib import Path

DAY_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = DAY_ROOT.parent

_CONFLICTING = {
    # Day 1 to 5 module names that may already be cached by pytest.
    "excel_writer", "pipeline", "csv_writer", "ratios", "sectors",
    "pdf_loader", "invoice_schema", "main", "server", "ledger",
    "variance", "budget_schema", "cost_log", "pptx_writer", "pdf_writer",
    "history_store", "comparison", "run_cache", "power_bi",
    "cashflow_schema", "cashflow_maths", "scenario",
    "news_schema", "aggregation", "sentiment", "chart",
    "corrections", "live_fetcher", "industries",
    "pulse_pptx", "pulse_pdf",
    # Day 6 names.
    "cvp_schema", "cvp_maths", "cvp_chart", "cvp_excel", "cvp_csv",
    "break_pptx", "break_pdf", "monte_carlo", "benchmarks",
    # Day 7 names (cross-day eviction).
    "transcript_schema", "analysis", "hedge_phrases", "claims", "edgar",
    "brief_chart",
}


def _evict_and_set_path() -> None:
    for name in list(_CONFLICTING):
        sys.modules.pop(name, None)
    for p in (str(DAY_ROOT), str(PROJECT_ROOT)):
        if p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, str(DAY_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))


_evict_and_set_path()


def pytest_collectstart(collector):
    p = getattr(collector, "path", None) or getattr(collector, "fspath", None)
    if p is None:
        return
    if str(DAY_ROOT) in str(p):
        _evict_and_set_path()


import pytest


@pytest.fixture(autouse=True)
def _ensure_day_path():
    """Re-evict + reset sys.path before every Day 6 test, so cross-day
    pollution from later-collected days (e.g. Day 7's pipeline.py) does not
    leak into Day 6's imports during the full-suite run."""
    _evict_and_set_path()
    yield


for p in (str(DAY_ROOT), str(PROJECT_ROOT)):
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, str(DAY_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))
