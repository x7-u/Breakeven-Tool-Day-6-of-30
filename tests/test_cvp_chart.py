"""Day 6. Smoke tests for chart rendering."""
from __future__ import annotations

from cvp_chart import render_breakeven_png, render_breakeven_svg, render_tornado_png
from cvp_maths import TornadoEntry
from cvp_schema import CVPInputs


def _inp() -> CVPInputs:
    return CVPInputs(fixed_cost=1000, variable_cost_per_unit=2.0, price_per_unit=5.0)


def test_breakeven_png_smoke():
    data = render_breakeven_png(
        _inp(), title="Test", currency="GBP", current_volume=400,
    )
    assert isinstance(data, bytes)
    assert len(data) > 4000  # PNG header + minimal content
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_tornado_png_smoke():
    rows = [
        TornadoEntry("price_per_unit", 50, -45, 50),
        TornadoEntry("variable_cost_per_unit", 30, -25, 30),
        TornadoEntry("fixed_cost", 10, -10, 10),
    ]
    data = render_tornado_png(rows, title="Tornado")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) > 1500


def test_breakeven_svg_well_formed():
    svg = render_breakeven_svg(_inp(), currency="GBP", current_volume=400)
    assert svg.startswith("<svg ")
    assert svg.endswith("</svg>")
    # Magenta BE marker present
    assert "#EC4899" in svg
    # Purple revenue line present
    assert "#7C3AED" in svg
