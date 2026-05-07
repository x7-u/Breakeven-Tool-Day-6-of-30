"""Day 6. Tests for cvp_schema.parse_inputs."""
from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest
from cvp_schema import CVPInputs, CVPMetadata, parse_inputs


def _book(metadata_rows, ue_rows) -> bytes:
    wb = openpyxl.Workbook()
    md = wb.active
    md.title = "metadata"
    md.append(["key", "value"])
    for k, v in metadata_rows:
        md.append([k, v])
    ue = wb.create_sheet("unit_economics")
    ue.append(["key", "value"])
    for k, v in ue_rows:
        ue.append([k, v])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parses_minimal_workbook():
    data = _book(
        [("company", "Acme"), ("currency", "GBP"), ("period_label", "2026-Q2")],
        [("fixed_cost", 1000), ("variable_cost_per_unit", 2.0), ("price_per_unit", 5.0)],
    )
    parsed = parse_inputs(file_bytes=data)
    assert parsed.metadata.company == "Acme"
    assert parsed.metadata.currency == "GBP"
    assert parsed.inputs.fixed_cost == 1000
    assert parsed.inputs.variable_cost_per_unit == 2.0
    assert parsed.inputs.price_per_unit == 5.0
    assert parsed.inputs.target_profit is None


def test_parses_target_profit_and_current_volume():
    data = _book(
        [("company", "Acme"), ("currency", "USD"),
         ("period_label", "2026-04"), ("current_volume", 1500)],
        [("fixed_cost", 1000), ("variable_cost_per_unit", 2.0),
         ("price_per_unit", 5.0), ("target_profit", 500)],
    )
    parsed = parse_inputs(file_bytes=data)
    assert parsed.metadata.current_volume == 1500
    assert parsed.inputs.target_profit == 500


def test_rejects_missing_metadata_keys():
    data = _book(
        [("company", "Acme"), ("currency", "GBP")],   # period_label missing
        [("fixed_cost", 1000), ("variable_cost_per_unit", 2.0), ("price_per_unit", 5.0)],
    )
    with pytest.raises(ValueError, match="metadata"):
        parse_inputs(file_bytes=data)


def test_rejects_missing_unit_economics_keys():
    data = _book(
        [("company", "Acme"), ("currency", "GBP"), ("period_label", "P")],
        [("fixed_cost", 1000), ("variable_cost_per_unit", 2.0)],  # price missing
    )
    with pytest.raises(ValueError, match="unit_economics"):
        parse_inputs(file_bytes=data)


def test_rejects_zero_price():
    data = _book(
        [("company", "Acme"), ("currency", "GBP"), ("period_label", "P")],
        [("fixed_cost", 1000), ("variable_cost_per_unit", 0), ("price_per_unit", 0)],
    )
    with pytest.raises(ValueError):
        parse_inputs(file_bytes=data)


def test_rejects_vc_above_or_equal_price():
    data = _book(
        [("company", "Acme"), ("currency", "GBP"), ("period_label", "P")],
        [("fixed_cost", 1000), ("variable_cost_per_unit", 5.0), ("price_per_unit", 5.0)],
    )
    with pytest.raises(ValueError, match="breaks? even"):
        parse_inputs(file_bytes=data)


def test_warns_on_non_numeric_current_volume():
    data = _book(
        [("company", "Acme"), ("currency", "GBP"),
         ("period_label", "P"), ("current_volume", "lots")],
        [("fixed_cost", 1000), ("variable_cost_per_unit", 2.0), ("price_per_unit", 5.0)],
    )
    parsed = parse_inputs(file_bytes=data)
    assert parsed.metadata.current_volume is None
    assert any("current_volume" in w for w in parsed.warnings)


def test_currency_uppercased():
    data = _book(
        [("company", "Acme"), ("currency", "gbp"), ("period_label", "P")],
        [("fixed_cost", 1000), ("variable_cost_per_unit", 2.0), ("price_per_unit", 5.0)],
    )
    parsed = parse_inputs(file_bytes=data)
    assert parsed.metadata.currency == "GBP"


def test_round_trip_via_path(tmp_path: Path):
    data = _book(
        [("company", "Acme"), ("currency", "GBP"), ("period_label", "P")],
        [("fixed_cost", 1000), ("variable_cost_per_unit", 2.0), ("price_per_unit", 5.0)],
    )
    p = tmp_path / "x.xlsx"
    p.write_bytes(data)
    parsed = parse_inputs(path=p)
    assert parsed.inputs.fixed_cost == 1000
