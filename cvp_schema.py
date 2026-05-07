"""Day 6. Input parsing for the BREAK CVP tool.

XLSX shape:
  metadata sheet (key | value):
    company, currency, period_label.
    Optional: current_volume, capacity_units, non_cash_amount, industry.
  unit_economics sheet (key | value):
    fixed_cost, variable_cost_per_unit, price_per_unit.
    Optional: target_profit.
  products sheet (optional, columns: name | price_per_unit | variable_cost_per_unit | mix_pct):
    Multi-product mix. mix_pct sums to 1.0 (auto-normalised if it does not).
  step_costs sheet (optional, columns: above_units | extra_fixed_cost):
    Step changes in fixed cost above given volume thresholds.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class CVPMetadata:
    company: str
    currency: str
    period_label: str
    current_volume: float | None = None      # for margin of safety
    capacity_units: float | None = None      # max units the model can deliver
    non_cash_amount: float | None = None     # depreciation/amortisation; for cash BE
    industry: str | None = None              # for benchmark overlay
    covenant_min_revenue: float | None = None  # bank covenant: min revenue per period


@dataclass
class VolumePoint:
    """A planned volume target at a labelled period (e.g. 2026-W18)."""
    period_label: str
    units: float


@dataclass
class CVPInputs:
    fixed_cost: float
    variable_cost_per_unit: float
    price_per_unit: float
    target_profit: float | None = None


@dataclass
class Product:
    name: str
    price_per_unit: float
    variable_cost_per_unit: float
    mix_pct: float                           # 0.0 - 1.0


@dataclass
class StepCost:
    above_units: float                       # threshold
    extra_fixed_cost: float                  # added on top of base fixed


@dataclass
class ParsedInputs:
    metadata: CVPMetadata
    inputs: CVPInputs
    warnings: list[str]
    products: list[Product] = field(default_factory=list)
    step_costs: list[StepCost] = field(default_factory=list)
    volume_curve: list[VolumePoint] = field(default_factory=list)


_REQUIRED_META = {"company", "currency", "period_label"}
_REQUIRED_INPUTS = {"fixed_cost", "variable_cost_per_unit", "price_per_unit"}


def parse_inputs(*, file_bytes: bytes | None = None,
                 path: Path | str | None = None,
                 source_filename: str = "") -> ParsedInputs:
    if file_bytes is not None:
        buf: io.BytesIO | Path = io.BytesIO(file_bytes)
    elif path is not None:
        buf = Path(path)
    else:
        raise ValueError("parse_inputs() needs either file_bytes or path.")
    try:
        xl = pd.ExcelFile(buf, engine="openpyxl")
    except Exception as e:
        raise ValueError(f"Could not open workbook: {e}") from e

    sheets = {n.strip().lower(): n for n in xl.sheet_names}
    for required in ("metadata", "unit_economics"):
        if required not in sheets:
            raise ValueError(
                f"Workbook missing required sheet '{required}'. "
                "Expected metadata + unit_economics."
            )

    warnings: list[str] = []
    metadata = _parse_metadata(xl, sheets["metadata"], warnings)
    inputs = _parse_unit_economics(xl, sheets["unit_economics"], warnings)
    products: list[Product] = []
    step_costs: list[StepCost] = []
    volume_curve: list[VolumePoint] = []
    if "products" in sheets:
        products = _parse_products(xl, sheets["products"], warnings)
    if "step_costs" in sheets:
        step_costs = _parse_step_costs(xl, sheets["step_costs"], warnings)
    if "volume_curve" in sheets:
        volume_curve = _parse_volume_curve(xl, sheets["volume_curve"], warnings)

    if inputs.price_per_unit <= 0:
        raise ValueError("price_per_unit must be > 0.")
    if inputs.variable_cost_per_unit < 0:
        raise ValueError("variable_cost_per_unit must be >= 0.")
    if inputs.fixed_cost < 0:
        raise ValueError("fixed_cost must be >= 0.")
    if inputs.variable_cost_per_unit >= inputs.price_per_unit:
        raise ValueError(
            f"variable_cost_per_unit ({inputs.variable_cost_per_unit}) "
            f">= price_per_unit ({inputs.price_per_unit}). "
            "Contribution margin would be zero or negative; the business "
            "model never breaks even at any volume. Please re-check inputs."
        )

    return ParsedInputs(
        metadata=metadata, inputs=inputs, warnings=warnings,
        products=products, step_costs=step_costs,
        volume_curve=volume_curve,
    )


def _kv_pairs(df: pd.DataFrame) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for _, row in df.iterrows():
        key = str(row.iloc[0] or "").strip().lower()
        if not key or key in {"key", "metadata"}:
            continue
        val = row.iloc[1] if df.shape[1] > 1 else ""
        pairs[key] = "" if pd.isna(val) else str(val).strip()
    return pairs


def _parse_metadata(xl, sheet_name: str, warnings: list[str]) -> CVPMetadata:
    df = xl.parse(sheet_name, header=None)
    if df.shape[1] < 2:
        raise ValueError("'metadata' must have two columns: key | value.")
    pairs = _kv_pairs(df)
    missing = _REQUIRED_META - pairs.keys()
    if missing:
        raise ValueError(
            f"'metadata' missing keys: {sorted(missing)}. "
            f"Required: {sorted(_REQUIRED_META)}."
        )
    cv_val = _opt_float(pairs.get("current_volume", ""), "current_volume", warnings)
    cap_val = _opt_float(pairs.get("capacity_units", ""), "capacity_units", warnings)
    non_cash = _opt_float(pairs.get("non_cash_amount", ""), "non_cash_amount", warnings)
    covenant = _opt_float(pairs.get("covenant_min_revenue", ""),
                          "covenant_min_revenue", warnings)
    industry = pairs.get("industry", "").strip() or None
    return CVPMetadata(
        company=pairs["company"] or "Unknown",
        currency=pairs["currency"].upper() or "GBP",
        period_label=pairs["period_label"] or "",
        current_volume=cv_val,
        capacity_units=cap_val,
        non_cash_amount=non_cash,
        industry=industry,
        covenant_min_revenue=covenant,
    )


def _parse_unit_economics(xl, sheet_name: str, warnings: list[str]) -> CVPInputs:
    df = xl.parse(sheet_name, header=None)
    if df.shape[1] < 2:
        raise ValueError("'unit_economics' must have two columns: key | value.")
    pairs = _kv_pairs(df)
    missing = _REQUIRED_INPUTS - pairs.keys()
    if missing:
        raise ValueError(
            f"'unit_economics' missing keys: {sorted(missing)}. "
            f"Required: {sorted(_REQUIRED_INPUTS)}."
        )

    def _num(key: str, *, allow_zero: bool = False) -> float:
        try:
            v = float(str(pairs[key]).replace(",", ""))
        except (ValueError, KeyError) as e:
            raise ValueError(f"{key} must be numeric. Got: {pairs.get(key)!r}") from e
        if not allow_zero and v == 0 and key == "price_per_unit":
            raise ValueError(f"{key} cannot be zero.")
        return v

    target: float | None = None
    if pairs.get("target_profit"):
        try:
            target = float(str(pairs["target_profit"]).replace(",", ""))
        except ValueError:
            warnings.append("target_profit not numeric; ignored.")

    return CVPInputs(
        fixed_cost=_num("fixed_cost", allow_zero=True),
        variable_cost_per_unit=_num("variable_cost_per_unit", allow_zero=True),
        price_per_unit=_num("price_per_unit"),
        target_profit=target,
    )


def _parse_products(xl, sheet_name: str, warnings: list[str]) -> list[Product]:
    df = xl.parse(sheet_name)
    if df.empty:
        return []
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"name", "price_per_unit", "variable_cost_per_unit", "mix_pct"}
    missing = required - set(df.columns)
    if missing:
        warnings.append(
            f"products sheet missing columns {sorted(missing)}; ignored."
        )
        return []
    out: list[Product] = []
    for _, row in df.iterrows():
        name = str(row["name"] or "").strip()
        if not name:
            continue
        try:
            price = float(row["price_per_unit"])
            vc = float(row["variable_cost_per_unit"])
            mix = float(row["mix_pct"])
        except (ValueError, TypeError):
            warnings.append(f"products row '{name}' not numeric; skipped.")
            continue
        if price <= 0 or vc < 0:
            warnings.append(f"products row '{name}' has invalid price/vc; skipped.")
            continue
        out.append(Product(name=name, price_per_unit=price,
                           variable_cost_per_unit=vc, mix_pct=mix))
    if not out:
        return []
    total = sum(p.mix_pct for p in out)
    if total <= 0:
        warnings.append("products mix_pct sums to 0; ignored.")
        return []
    if abs(total - 1.0) > 0.01:
        warnings.append(f"products mix_pct sums to {total:.3f}; auto-normalised to 1.0.")
        out = [Product(p.name, p.price_per_unit, p.variable_cost_per_unit, p.mix_pct / total)
               for p in out]
    return out


def _parse_step_costs(xl, sheet_name: str, warnings: list[str]) -> list[StepCost]:
    df = xl.parse(sheet_name)
    if df.empty:
        return []
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"above_units", "extra_fixed_cost"}
    missing = required - set(df.columns)
    if missing:
        warnings.append(f"step_costs sheet missing columns {sorted(missing)}; ignored.")
        return []
    out: list[StepCost] = []
    for _, row in df.iterrows():
        try:
            au = float(row["above_units"])
            ef = float(row["extra_fixed_cost"])
        except (ValueError, TypeError):
            continue
        if au < 0 or ef < 0:
            continue
        out.append(StepCost(above_units=au, extra_fixed_cost=ef))
    out.sort(key=lambda s: s.above_units)
    return out


def _parse_volume_curve(xl, sheet_name: str, warnings: list[str]) -> list[VolumePoint]:
    df = xl.parse(sheet_name)
    if df.empty:
        return []
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = {"period_label", "units"}
    missing = required - set(df.columns)
    if missing:
        warnings.append(
            f"volume_curve sheet missing columns {sorted(missing)}; ignored."
        )
        return []
    import math as _m
    out: list[VolumePoint] = []
    for _, row in df.iterrows():
        raw_label = row["period_label"]
        if raw_label is None or (isinstance(raw_label, float) and _m.isnan(raw_label)):
            continue
        label = str(raw_label).strip()
        if not label or label.lower() == "nan":
            continue
        try:
            u = float(row["units"])
            if _m.isnan(u):
                raise ValueError("nan")
        except (ValueError, TypeError):
            warnings.append(f"volume_curve row '{label}' units not numeric; skipped.")
            continue
        if u < 0:
            continue
        out.append(VolumePoint(period_label=label, units=u))
    return out


def _opt_float(s: str, name: str, warnings: list[str]) -> float | None:
    if not s:
        return None
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        warnings.append(f"{name} not numeric ({s!r}); ignored.")
        return None
