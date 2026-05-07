"""Day 6. CLI entry for the BREAK CVP tool.

Usage:
  python main.py path/to/workbook.xlsx
  python main.py --sample coffee_shop
  python main.py --sample software_saas --no-ai
  python main.py path/to/workbook.xlsx --model deepseek-chat --max-cost 0.01
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
SAMPLE_DIR = HERE / "sample_data"
OUTPUTS = HERE / "outputs"

SAMPLES = {
    "coffee_shop":      "sample_coffee_shop.xlsx",
    "low_cost_airline": "sample_low_cost_airline.xlsx",
    "software_saas":    "sample_software_saas.xlsx",
    "brew_and_bites":   "sample_brew_and_bites.xlsx",
}


def main():
    p = argparse.ArgumentParser(description="Day 6 BREAK CVP analyser (CLI).")
    p.add_argument("workbook", nargs="?", help="path to .xlsx workbook")
    p.add_argument("--sample", choices=sorted(SAMPLES.keys()),
                   help="Use a bundled sample instead of a workbook path.")
    p.add_argument("--no-ai", action="store_true", help="Skip the DeepSeek call.")
    p.add_argument("--model", default=None, help="Override model (e.g. deepseek-chat).")
    p.add_argument("--api-key", default=None, help="Override DeepSeek API key.")
    p.add_argument("--max-cost", type=float, default=None,
                   help="USD guardrail; raise this to allow pricier runs.")
    args = p.parse_args()

    from cvp_csv import write_csv
    from cvp_excel import write_workbook
    from pipeline import analyse

    if args.sample:
        path = SAMPLE_DIR / SAMPLES[args.sample]
    elif args.workbook:
        path = Path(args.workbook)
    else:
        p.error("Provide a workbook path or --sample.")
        return

    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)

    try:
        result = analyse(
            path=path, source_filename=path.name,
            skip_ai=args.no_ai, model=args.model, api_key=args.api_key,
            max_cost_usd=args.max_cost,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    h = result.cvp.headline
    md = result.cvp.metadata
    print(f"\n  BREAK | {md.company} | {md.period_label} | {md.currency}")
    if h.break_even_units == float("inf"):
        print("  Contribution margin <= 0; the model never breaks even.")
    else:
        print(f"  Break-even units    : {h.break_even_units:>12,.0f}")
        print(f"  Break-even revenue  : {h.break_even_revenue:>12,.0f} {md.currency}")
        print(f"  Contribution margin : {h.contribution_margin_per_unit:>12.2f} {md.currency}/unit")
        print(f"  CM ratio            : {h.cm_ratio:>12.2%}")
    if h.margin_of_safety_units is not None:
        print(f"  Margin of safety    : {h.margin_of_safety_units:>12,.0f} units "
              f"({(h.margin_of_safety_pct or 0):+.2%})")
    if h.target_profit_units is not None:
        print(f"  Target profit units : {h.target_profit_units:>12,.0f}")
    if h.operating_leverage_at_current is not None:
        print(f"  Operating leverage  : {h.operating_leverage_at_current:>12.2f}x")

    if not result.commentary.skipped and not result.commentary.error:
        print()
        print(f"  AI verdict          : {result.commentary.headline}")
        print(f"  AI cost (USD)       : {result.commentary.cost_usd:.5f}")

    OUTPUTS.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M")
    slug = "".join(ch if ch.isalnum() else "_" for ch in md.company.lower())[:32].strip("_")
    xlsx_path = OUTPUTS / f"break_{slug}_{ts}.xlsx"
    csv_path = OUTPUTS / f"break_{slug}_{ts}_sensitivity.csv"
    write_workbook(result.cvp, xlsx_path)
    write_csv(result.cvp, csv_path)
    print()
    print(f"  Wrote: {xlsx_path.relative_to(HERE)}")
    print(f"  Wrote: {csv_path.relative_to(HERE)}")
    print()


if __name__ == "__main__":
    main()
