"""Day 6. Flat sensitivity CSV.

Single CSV: one row per (variable, delta). Empty cells where BE is undefined
(contribution margin went to zero or negative under shock).

Encoding utf-8-sig so Excel auto-detects UTF-8.
"""
from __future__ import annotations

import csv
from pathlib import Path

from cvp_maths import CVPResult

COLUMNS = (
    "company", "currency", "period", "variable", "delta_pct", "new_value",
    "new_break_even_units", "swing_units", "swing_pct",
)


def write_csv(result: CVPResult, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = result.metadata
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for r in result.sensitivity:
            w.writerow([
                md.company,
                md.currency,
                md.period_label,
                r.variable,
                f"{r.delta_pct:.2f}",
                f"{r.new_value:.4f}",
                "" if r.new_break_even_units is None else f"{r.new_break_even_units:.2f}",
                "" if r.swing_units is None else f"{r.swing_units:.2f}",
                "" if r.swing_pct is None else f"{r.swing_pct:.4f}",
            ])
    return out_path
