"""Day 6. PDF export for the BREAK CVP tool.

Three A4 pages via matplotlib PdfPages:
  1. Cover with headline KPIs + AI verdict.
  2. Break-even chart full-bleed.
  3. Sensitivity tornado + actions.

Pure matplotlib (Agg backend), no third-party PDF library required.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from pathlib import Path

import matplotlib.pyplot as plt
from cvp_chart import GREY, INK, MAGENTA, PURPLE, render_breakeven_png, render_tornado_png
from cvp_maths import CVPResult
from matplotlib.backends.backend_pdf import PdfPages

A4_LANDSCAPE = (11.69, 8.27)


def _ccy_sym(c: str) -> str:
    return {"GBP": "£", "USD": "$", "EUR": "€"}.get(c.upper(), "")


def write_pdf(result: CVPResult, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = result.cvp.metadata
    inp = result.cvp.inputs
    h = result.cvp.headline
    sym = _ccy_sym(md.currency)

    with PdfPages(out_path) as pdf:
        # Page 1: cover
        fig = plt.figure(figsize=A4_LANDSCAPE)
        fig.patch.set_facecolor("white")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.text(0.05, 0.92, "BREAK", fontsize=22, fontweight="bold", color=PURPLE)
        ax.text(0.05, 0.87, "Day 06 . Cost-Volume-Profit", fontsize=10, color=GREY)
        ax.text(0.05, 0.78, md.company, fontsize=32, fontweight="bold", color=INK)
        ax.text(0.05, 0.73, f"{md.period_label}  |  {md.currency}", fontsize=12, color=GREY)
        if h.break_even_units == float("inf"):
            be_line = "Break-even: NEVER (contribution margin <= 0)"
        else:
            be_line = (f"Break-even: {h.break_even_units:,.0f} units  |  "
                       f"{sym}{h.break_even_revenue:,.0f} revenue  |  "
                       f"CM ratio {h.cm_ratio:.1%}")
        ax.text(0.05, 0.62, be_line, fontsize=14, color=INK)
        if h.margin_of_safety_units is not None:
            mos = h.margin_of_safety_pct or 0.0
            ax.text(0.05, 0.55,
                    f"Margin of safety: {h.margin_of_safety_units:,.0f} units ({mos:+.1%})",
                    fontsize=12, color=INK)
        if result.commentary and result.commentary.headline:
            ax.text(0.05, 0.40, result.commentary.headline,
                    fontsize=14, color=INK, wrap=True)
        if result.commentary and result.commentary.summary:
            ax.text(0.05, 0.30, result.commentary.summary,
                    fontsize=11, color=GREY, wrap=True)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 2: break-even chart
        png_bytes = render_breakeven_png(
            inp, title=f"Break-even chart {md.company}",
            currency=md.currency,
            current_volume=md.current_volume,
        )
        fig = _png_page(png_bytes)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # Page 3: sensitivity + actions
        fig = plt.figure(figsize=A4_LANDSCAPE)
        fig.patch.set_facecolor("white")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.axis("off")
        ax.text(0.05, 0.92, "Sensitivity & verdict", fontsize=20, fontweight="bold", color=INK)
        if result.cvp.tornado:
            png_t = render_tornado_png(result.cvp.tornado, title="BE swing per variable (+/-10%)")
            from io import BytesIO

            from matplotlib.image import imread
            img = imread(BytesIO(png_t))
            ax_img = fig.add_axes([0.05, 0.18, 0.55, 0.65])
            ax_img.imshow(img)
            ax_img.axis("off")
        if result.commentary and not result.commentary.skipped:
            c = result.commentary
            tx = 0.65
            ax.text(tx, 0.80, c.headline or "", fontsize=12, fontweight="bold",
                    color=INK, wrap=True)
            ax.text(tx, 0.70, c.summary or "", fontsize=10, color=INK, wrap=True)
            if c.risks:
                ax.text(tx, 0.52, "Risks:", fontsize=10, fontweight="bold", color=MAGENTA)
                for i, r in enumerate(c.risks[:4]):
                    ax.text(tx, 0.48 - i * 0.04, f"- {r}", fontsize=9, color=INK, wrap=True)
            if c.actions:
                ax.text(tx, 0.30, "Actions:", fontsize=10, fontweight="bold", color=PURPLE)
                for i, a in enumerate(c.actions[:4]):
                    ax.text(tx, 0.26 - i * 0.04, f"- {a}", fontsize=9, color=INK, wrap=True)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)
    return out_path


def _png_page(png_bytes: bytes):
    from io import BytesIO

    from matplotlib.image import imread
    img = imread(BytesIO(png_bytes))
    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.04, 0.04, 0.92, 0.92])
    ax.imshow(img)
    ax.axis("off")
    return fig
