"""Day 6. Charts for the BREAK CVP tool.

Two PNGs (matplotlib Agg) plus an inline SVG of the break-even chart for
the web UI.

1. Break-even chart: revenue line, total cost line, fixed cost line,
   filled profit / loss zones, BE point marker.
2. Tornado: horizontal bars per variable, sorted by abs_max_swing.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
from cvp_maths import TornadoEntry
from cvp_schema import CVPInputs

# BREAK palette (matches the live UI hex)
INK    = "#0F1117"
PURPLE = "#7C3AED"
MAGENTA = "#EC4899"
GREEN  = "#10B981"
RED    = "#EF4444"
GREY   = "#6B7280"
PANEL  = "#F7F8FA"


def render_breakeven_png(inputs: CVPInputs, *,
                         title: str,
                         currency: str = "GBP",
                         current_volume: float | None = None,
                         out_path: Path | None = None) -> bytes:
    cm = inputs.price_per_unit - inputs.variable_cost_per_unit
    be = inputs.fixed_cost / cm if cm > 0 else 0.0
    max_x = max(be * 2.0, current_volume or 0, 1.0)
    if max_x <= 0:
        max_x = 100
    x = [0, max_x]

    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=120)
    fig.patch.set_facecolor("white")
    ax.set_facecolor(PANEL)

    revenue = [0, inputs.price_per_unit * max_x]
    total_cost = [inputs.fixed_cost, inputs.fixed_cost + inputs.variable_cost_per_unit * max_x]
    fixed = [inputs.fixed_cost, inputs.fixed_cost]

    ax.fill_between(x, revenue, total_cost,
                    where=[a >= b for a, b in zip(revenue, total_cost, strict=True)],
                    color=GREEN, alpha=0.10, label="_nolegend_")
    ax.fill_between(x, revenue, total_cost,
                    where=[a < b for a, b in zip(revenue, total_cost, strict=True)],
                    color=RED, alpha=0.10, label="_nolegend_")

    ax.plot(x, revenue, color=PURPLE, linewidth=2.4, label=f"Revenue ({currency} {inputs.price_per_unit:.2f}/unit)")
    ax.plot(x, total_cost, color=INK, linewidth=2.0, label=f"Total cost (Fixed + {currency} {inputs.variable_cost_per_unit:.2f}/unit VC)")
    ax.plot(x, fixed, color=GREY, linewidth=1.2, linestyle="--", label=f"Fixed cost ({currency} {inputs.fixed_cost:,.0f})")

    if cm > 0 and be > 0:
        be_revenue = be * inputs.price_per_unit
        ax.axvline(be, color=MAGENTA, linewidth=1.2, linestyle=":")
        ax.scatter([be], [be_revenue], color=MAGENTA, s=80, zorder=5,
                   label=f"Break-even at {be:,.0f} units")

    if current_volume is not None and current_volume > 0:
        ax.axvline(current_volume, color=GREY, linewidth=0.7, linestyle=":")

    ax.set_xlabel("Volume (units)", fontsize=10, color=INK)
    ax.set_ylabel(f"Currency ({currency})", fontsize=10, color=INK)
    ax.set_title(title, fontsize=12, color=INK, pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", color=GREY, alpha=0.3)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    fig.tight_layout()
    return _flush(fig, out_path)


def render_tornado_png(tornado: list[TornadoEntry], *,
                       title: str,
                       out_path: Path | None = None) -> bytes:
    fig, ax = plt.subplots(figsize=(8, max(3, 0.6 * len(tornado) + 1.5)), dpi=120)
    fig.patch.set_facecolor("white")

    labels = [_pretty_name(t.variable) for t in tornado]
    minus = [t.swing_minus_10_pct for t in tornado]
    plus = [t.swing_plus_10_pct for t in tornado]

    y = list(range(len(labels)))
    ax.barh(y, minus, color=RED, alpha=0.7, label="-10% shift", height=0.6)
    ax.barh(y, plus, color=GREEN, alpha=0.7, label="+10% shift", height=0.6)
    ax.axvline(0, color=INK, linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("Change in break-even units", fontsize=10)
    ax.set_title(title, fontsize=12, color=INK, pad=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=9, frameon=False, loc="lower right")
    fig.tight_layout()
    return _flush(fig, out_path)


def render_breakeven_svg(inputs: CVPInputs, *,
                         currency: str = "GBP",
                         current_volume: float | None = None,
                         width: int = 920, height: int = 320, pad: int = 40) -> str:
    cm = inputs.price_per_unit - inputs.variable_cost_per_unit
    be = inputs.fixed_cost / cm if cm > 0 else 0.0
    max_x = max(be * 2.0, current_volume or 0, 1.0)
    revenue_at_max = inputs.price_per_unit * max_x
    cost_at_max = inputs.fixed_cost + inputs.variable_cost_per_unit * max_x
    max_y = max(revenue_at_max, cost_at_max, 1.0)

    inner_w = width - 2 * pad
    inner_h = height - 2 * pad

    def x_at(v: float) -> float:
        return pad + (v / max_x) * inner_w

    def y_at(v: float) -> float:
        return pad + (1 - v / max_y) * inner_h

    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="{height}">')
    parts.append(f'<rect width="{width}" height="{height}" fill="transparent"/>')
    # Frame
    parts.append(f'<rect x="{pad}" y="{pad}" width="{inner_w}" height="{inner_h}" fill="none" stroke="{GREY}" stroke-width="0.6"/>')
    # Profit / loss shading via simple polygons.
    if cm > 0 and be > 0 and be < max_x:
        # Loss triangle (0, fixed) to (be, be_rev) to (0, 0)
        parts.append(
            f'<polygon points="{x_at(0):.1f},{y_at(0):.1f} {x_at(be):.1f},{y_at(be * inputs.price_per_unit):.1f} {x_at(0):.1f},{y_at(inputs.fixed_cost):.1f}" fill="{RED}" opacity="0.10"/>'
        )
        # Profit area to the right
        parts.append(
            f'<polygon points="{x_at(be):.1f},{y_at(be * inputs.price_per_unit):.1f} {x_at(max_x):.1f},{y_at(revenue_at_max):.1f} {x_at(max_x):.1f},{y_at(cost_at_max):.1f}" fill="{GREEN}" opacity="0.10"/>'
        )
    # Lines
    parts.append(f'<line x1="{x_at(0):.1f}" y1="{y_at(0):.1f}" x2="{x_at(max_x):.1f}" y2="{y_at(revenue_at_max):.1f}" stroke="{PURPLE}" stroke-width="2.4"/>')
    parts.append(f'<line x1="{x_at(0):.1f}" y1="{y_at(inputs.fixed_cost):.1f}" x2="{x_at(max_x):.1f}" y2="{y_at(cost_at_max):.1f}" stroke="{INK}" stroke-width="2.0"/>')
    parts.append(f'<line x1="{x_at(0):.1f}" y1="{y_at(inputs.fixed_cost):.1f}" x2="{x_at(max_x):.1f}" y2="{y_at(inputs.fixed_cost):.1f}" stroke="{GREY}" stroke-width="1.0" stroke-dasharray="4 4"/>')
    if cm > 0 and be > 0:
        parts.append(f'<line x1="{x_at(be):.1f}" y1="{pad}" x2="{x_at(be):.1f}" y2="{pad + inner_h}" stroke="{MAGENTA}" stroke-width="1.0" stroke-dasharray="2 4"/>')
        parts.append(f'<circle cx="{x_at(be):.1f}" cy="{y_at(be * inputs.price_per_unit):.1f}" r="6" fill="{MAGENTA}"/>')
        parts.append(f'<text x="{x_at(be):.1f}" y="{pad + inner_h + 14:.1f}" font-family="Inter,sans-serif" font-size="10" fill="{MAGENTA}" text-anchor="middle">BE {be:,.0f}u</text>')
    if current_volume is not None and current_volume > 0:
        parts.append(f'<line x1="{x_at(current_volume):.1f}" y1="{pad}" x2="{x_at(current_volume):.1f}" y2="{pad + inner_h}" stroke="{GREY}" stroke-width="0.7" stroke-dasharray="1 3"/>')
        parts.append(f'<text x="{x_at(current_volume):.1f}" y="{pad - 4:.1f}" font-family="Inter,sans-serif" font-size="10" fill="{GREY}" text-anchor="middle">Today {current_volume:,.0f}u</text>')
    # Axis labels
    parts.append(f'<text x="{width / 2:.1f}" y="{height - 6:.1f}" font-family="Inter,sans-serif" font-size="10" fill="{GREY}" text-anchor="middle">Volume (units)</text>')
    parts.append(f'<text x="{14:.1f}" y="{height / 2:.1f}" font-family="Inter,sans-serif" font-size="10" fill="{GREY}" text-anchor="middle" transform="rotate(-90 14 {height / 2:.1f})">Currency ({currency})</text>')
    parts.append("</svg>")
    return "".join(parts)


def _pretty_name(var: str) -> str:
    return {
        "price_per_unit": "Price per unit",
        "variable_cost_per_unit": "Variable cost / unit",
        "fixed_cost": "Fixed cost",
    }.get(var, var)


def _flush(fig, out_path: Path | None) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    data = buf.getvalue()
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
    return data
