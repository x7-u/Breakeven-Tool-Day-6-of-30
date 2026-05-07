"""Day 6. Orchestrator for the BREAK CVP tool.

analyse():
  1. parse_inputs() reads the workbook.
  2. cvp_maths.headline_stats() + sensitivity_table() + tornado() do the maths.
  3. ONE DeepSeek V4 call interprets the business model and the
     sensitivity profile (single call, ~$0.0001 per run).

Idempotent: identical inputs short-circuit to the cached AI result.
Cost guardrail via DAY06_MAX_COST_USD (default $0.05).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks import lookup as lookup_benchmark
from cvp_maths import (
    SENSITIVITY_VARIABLES,
    CVPResult,
    first_crossing_period,
    headline_stats,
    heatmap_grid,
    multi_product_stats,
    sensitivity_table,
    step_cost_be,
    time_phased_be,
    tornado,
)
from cvp_schema import CVPInputs, CVPMetadata, parse_inputs
from monte_carlo import simulate as mc_simulate

from shared.config import DEEPSEEK_MODEL_FAST
from shared.deepseek_client import ask_deepseek_json_with_stats

DEFAULT_COST_GUARDRAIL_USD = float(os.getenv("DAY06_MAX_COST_USD", "0.05"))
TRACE_DIR = Path(__file__).resolve().parent / "outputs" / "traces"
HASH_CACHE_DIR = Path(__file__).resolve().parent / "outputs" / "hash_cache"


@dataclass
class Commentary:
    headline: str = ""
    summary: str = ""
    risks: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_tokens: int = 0
    model: str = ""
    skipped: bool = False
    error: str | None = None


@dataclass
class AnalysisResult:
    cvp: CVPResult
    warnings: list[str]
    commentary: Commentary
    source_filename: str = ""
    elapsed_ms: int = 0

    @property
    def total_cost_usd(self) -> float:
        return self.commentary.cost_usd or 0.0


def _content_hash(metadata: CVPMetadata, inputs: CVPInputs) -> str:
    payload = {
        "company": metadata.company,
        "currency": metadata.currency,
        "period": metadata.period_label,
        "current_volume": metadata.current_volume,
        "fixed_cost": round(inputs.fixed_cost, 4),
        "variable_cost_per_unit": round(inputs.variable_cost_per_unit, 4),
        "price_per_unit": round(inputs.price_per_unit, 4),
        "target_profit": (None if inputs.target_profit is None
                          else round(inputs.target_profit, 4)),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def estimate_cost() -> float:
    """Rough cost: ~250 tokens in + 350 tokens out at deepseek-chat rates."""
    return (250 * 0.27 + 350 * 1.10) / 1_000_000


def analyse(
    *,
    file_bytes: bytes | None = None,
    path: Path | str | None = None,
    source_filename: str = "",
    skip_ai: bool = False,
    model: str | None = None,
    api_key: str | None = None,
    use_cache: bool = True,
    max_cost_usd: float | None = None,
) -> AnalysisResult:
    started = _time.time()

    parsed = parse_inputs(file_bytes=file_bytes, path=path, source_filename=source_filename)
    md = parsed.metadata
    inp = parsed.inputs

    h = headline_stats(inp, md)
    sens = sensitivity_table(inp)
    tor = tornado(sens)
    mp = multi_product_stats(parsed.products, inp.fixed_cost) if parsed.products else None
    sc = step_cost_be(inp, parsed.step_costs) if parsed.step_costs else []
    tp = time_phased_be(inp, parsed.volume_curve) if parsed.volume_curve else []
    cvp = CVPResult(
        metadata=md, inputs=inp, headline=h,
        sensitivity=sens, tornado=tor,
        multi_product=mp, step_cost_be=sc,
        time_phased=tp,
    )

    if not skip_ai:
        budget = max_cost_usd if max_cost_usd is not None else DEFAULT_COST_GUARDRAIL_USD
        est = estimate_cost()
        if budget and est > budget:
            raise ValueError(
                f"Estimated AI cost ${est:.4f} exceeds guardrail ${budget:.4f}. "
                "Raise DAY06_MAX_COST_USD or pass max_cost_usd."
            )

    chash = _content_hash(md, inp)
    chosen_model = model or DEEPSEEK_MODEL_FAST

    if use_cache and not skip_ai:
        cache_path = _hash_cache_path(chash, model=chosen_model)
        cached = _load_cached_commentary(cache_path)
        if cached is not None:
            parsed.warnings.append("Cache hit on inputs hash, AI call skipped (cost saved).")
            elapsed_ms = int((_time.time() - started) * 1000)
            return AnalysisResult(
                cvp=cvp, warnings=parsed.warnings,
                commentary=cached, source_filename=source_filename,
                elapsed_ms=elapsed_ms,
            )

    if skip_ai:
        commentary = Commentary(skipped=True)
    else:
        commentary = narrate(cvp=cvp, model=model, api_key=api_key)

    elapsed_ms = int((_time.time() - started) * 1000)
    result = AnalysisResult(
        cvp=cvp, warnings=parsed.warnings,
        commentary=commentary, source_filename=source_filename,
        elapsed_ms=elapsed_ms,
    )

    try:
        _write_trace(chash, result)
    except Exception:
        pass
    if use_cache and not skip_ai and not commentary.error:
        try:
            _write_cached_commentary(_hash_cache_path(chash, model=chosen_model), commentary)
        except Exception:
            pass
    return result


def _hash_cache_path(content_hash: str, *, model: str) -> Path:
    safe_model = "".join(ch if ch.isalnum() else "_" for ch in model)[:30]
    return HASH_CACHE_DIR / f"{content_hash}_{safe_model}.json"


def _load_cached_commentary(cache_path: Path) -> Commentary | None:
    if not cache_path.is_file():
        return None
    try:
        d = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return Commentary(
        headline=d.get("headline", ""),
        summary=d.get("summary", ""),
        risks=list(d.get("risks", []) or []),
        actions=list(d.get("actions", []) or []),
        cost_usd=0.0,
        input_tokens=int(d.get("input_tokens", 0)),
        output_tokens=int(d.get("output_tokens", 0)),
        cache_hit_tokens=int(d.get("cache_hit_tokens", 0)),
        model=d.get("model", ""),
        skipped=False,
        error=None,
    )


def _write_cached_commentary(cache_path: Path, c: Commentary) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "headline": c.headline,
        "summary": c.summary,
        "risks": list(c.risks),
        "actions": list(c.actions),
        "input_tokens": c.input_tokens,
        "output_tokens": c.output_tokens,
        "cache_hit_tokens": c.cache_hit_tokens,
        "model": c.model,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_trace(content_hash: str, result: AnalysisResult) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now(_dt.UTC).replace(microsecond=0, tzinfo=None).isoformat() + "Z"
    rec = {
        "ts": ts,
        "content_hash": content_hash,
        "company": result.cvp.metadata.company,
        "currency": result.cvp.metadata.currency,
        "be_units": (None if result.cvp.headline.break_even_units in (float("inf"),) else
                     round(result.cvp.headline.break_even_units, 2)),
        "cm_ratio": round(result.cvp.headline.cm_ratio, 4),
        "ai_cost_usd": round(result.total_cost_usd, 6),
        "ai_model": result.commentary.model,
        "ai_error": result.commentary.error,
        "elapsed_ms": result.elapsed_ms,
    }
    path = TRACE_DIR / "traces.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---- AI commentary --------------------------------------------------

NARRATE_SYSTEM_PROMPT = (
    "You are a CFO advising a founder on whether their cost structure works. "
    "Given the break-even maths and the sensitivity table, judge whether the "
    "business model is viable, what the dominant risk variable is (price, "
    "variable cost, or fixed cost), and what to do about it. Speak plainly. "
    "Two to three sentences in the summary. Do not restate the input numbers; "
    "interpret them. Material insight first."
)

_NARRATE_SCHEMA = (
    '{\n'
    '  "headline": "1 sentence verdict on the business model",\n'
    '  "summary":  "2 to 3 sentences interpreting the maths",\n'
    '  "risks":    ["dominant risk variable + why", "second risk if material"],\n'
    '  "actions":  ["short imperative for the founder", "short imperative"]\n'
    '}'
)


def narrate(*, cvp: CVPResult,
            model: str | None = None,
            api_key: str | None = None) -> Commentary:
    digest = _build_digest(cvp)
    sys_prompt = NARRATE_SYSTEM_PROMPT + "\n\nSchema for your reply:\n" + _NARRATE_SCHEMA
    try:
        data, stats = ask_deepseek_json_with_stats(
            digest, system=sys_prompt, max_tokens=500,
            model=(model or DEEPSEEK_MODEL_FAST), api_key=api_key,
        )
    except Exception as e:
        return Commentary(
            headline=f"[AI commentary unavailable: {_scrub(e)}]",
            error=_scrub(e),
            model=model or DEEPSEEK_MODEL_FAST,
        )
    return Commentary(
        headline=str(data.get("headline") or "")[:280],
        summary=str(data.get("summary") or ""),
        risks=[str(x) for x in (data.get("risks") or [])][:5],
        actions=[str(x) for x in (data.get("actions") or [])][:5],
        cost_usd=stats.cost_usd,
        input_tokens=stats.input_tokens,
        output_tokens=stats.output_tokens,
        cache_hit_tokens=stats.cache_hit_tokens,
        model=stats.model,
    )


def _build_digest(cvp: CVPResult) -> str:
    md = cvp.metadata
    inp = cvp.inputs
    h = cvp.headline
    lines: list[str] = []
    lines.append(f"Subject: {md.company}  |  Period: {md.period_label}  |  Currency: {md.currency}")
    lines.append("")
    lines.append("Unit economics (per unit unless stated):")
    lines.append(f"  price={inp.price_per_unit:.2f}  vc={inp.variable_cost_per_unit:.2f}  "
                 f"fixed={inp.fixed_cost:.0f}  cm={h.contribution_margin_per_unit:.2f}  "
                 f"cm_ratio={h.cm_ratio:.3f}")
    if h.break_even_units == float('inf'):
        lines.append("  break_even_units=NEVER (contribution margin <= 0)")
    else:
        lines.append(f"  break_even_units={h.break_even_units:,.0f}  "
                     f"break_even_revenue={h.break_even_revenue:,.0f}")
    if md.current_volume is not None:
        lines.append(f"  current_volume={md.current_volume:,.0f}")
    if h.margin_of_safety_units is not None:
        mos_pct = h.margin_of_safety_pct if h.margin_of_safety_pct is not None else 0.0
        lines.append(f"  margin_of_safety_units={h.margin_of_safety_units:,.0f}  "
                     f"margin_of_safety_pct={mos_pct:+.2%}")
    if h.target_profit_units is not None:
        lines.append(f"  target_profit_units={h.target_profit_units:,.0f}")
    if h.operating_leverage_at_current is not None:
        lines.append(f"  operating_leverage_at_current={h.operating_leverage_at_current:.2f}")
    lines.append("")
    lines.append("Sensitivity (single-variable shocks, change in BE units):")
    pretty = {
        "price_per_unit": "price",
        "variable_cost_per_unit": "vc",
        "fixed_cost": "fixed",
    }
    for var in SENSITIVITY_VARIABLES:
        rows = [s for s in cvp.sensitivity if s.variable == var and s.delta_pct != 0.0]
        bits = []
        for r in rows:
            if r.swing_units is None:
                bits.append(f"{r.delta_pct:+.0%}: NEVER")
            else:
                bits.append(f"{r.delta_pct:+.0%}: {r.swing_units:+,.0f}u")
        lines.append(f"  {pretty[var]}: " + "  ".join(bits))
    if cvp.tornado:
        top = cvp.tornado[0]
        lines.append("")
        lines.append(f"Dominant lever (largest abs swing on +/-10%): {pretty.get(top.variable, top.variable)}")
    return "\n".join(lines)


def to_dict(result: AnalysisResult) -> dict[str, Any]:
    cvp = result.cvp
    h = cvp.headline
    bench = lookup_benchmark(cvp.metadata.industry)
    grid = heatmap_grid(cvp.inputs)
    # Monte Carlo always runs (deterministic, ~50ms). Caller can override span.
    mc = mc_simulate(cvp.inputs, n_runs=4000, span_pct=0.20, seed=42)
    return {
        "metadata": {
            "company": cvp.metadata.company,
            "currency": cvp.metadata.currency,
            "period_label": cvp.metadata.period_label,
            "current_volume": cvp.metadata.current_volume,
            "capacity_units": cvp.metadata.capacity_units,
            "non_cash_amount": cvp.metadata.non_cash_amount,
            "industry": cvp.metadata.industry,
        },
        "inputs": {
            "fixed_cost": cvp.inputs.fixed_cost,
            "variable_cost_per_unit": cvp.inputs.variable_cost_per_unit,
            "price_per_unit": cvp.inputs.price_per_unit,
            "target_profit": cvp.inputs.target_profit,
        },
        "headline": {
            "contribution_margin_per_unit": h.contribution_margin_per_unit,
            "cm_ratio": h.cm_ratio,
            "break_even_units": (None if h.break_even_units == float("inf")
                                 else h.break_even_units),
            "break_even_revenue": (None if h.break_even_revenue == float("inf")
                                   else h.break_even_revenue),
            "margin_of_safety_units": h.margin_of_safety_units,
            "margin_of_safety_pct": h.margin_of_safety_pct,
            "target_profit_units": h.target_profit_units,
            "target_profit_revenue": h.target_profit_revenue,
            "operating_leverage_at_current": h.operating_leverage_at_current,
            "cash_break_even_units": h.cash_break_even_units,
            "capacity_units": h.capacity_units,
            "capacity_reachable": h.capacity_reachable,
            "capacity_buffer_pct": h.capacity_buffer_pct,
            "covenant_min_revenue": h.covenant_min_revenue,
            "covenant_breach": h.covenant_breach,
            "covenant_buffer_pct": h.covenant_buffer_pct,
        },
        "multi_product": (
            None if cvp.multi_product is None else {
                "weighted_price": cvp.multi_product.weighted_price,
                "weighted_variable_cost": cvp.multi_product.weighted_variable_cost,
                "weighted_cm_per_unit": cvp.multi_product.weighted_cm_per_unit,
                "weighted_cm_ratio": cvp.multi_product.weighted_cm_ratio,
                "blended_break_even_units": (None
                    if cvp.multi_product.blended_break_even_units == float("inf")
                    else cvp.multi_product.blended_break_even_units),
                "blended_break_even_revenue": (None
                    if cvp.multi_product.blended_break_even_revenue == float("inf")
                    else cvp.multi_product.blended_break_even_revenue),
                "per_product": [
                    {**p, "allocated_units": (None if p["allocated_units"] == float("inf")
                                              else p["allocated_units"]),
                          "allocated_revenue": (None if p["allocated_revenue"] == float("inf")
                                                else p["allocated_revenue"])}
                    for p in cvp.multi_product.per_product
                ],
            }
        ),
        "step_cost_be": [
            {
                "segment": s.segment,
                "fixed_cost_at_segment": s.fixed_cost_at_segment,
                "units_lower": s.units_lower,
                "units_upper": s.units_upper,
                "break_even_units": s.break_even_units,
                "is_reachable_in_segment": s.is_reachable_in_segment,
            }
            for s in cvp.step_cost_be
        ],
        "benchmark": (None if bench is None else {
            "industry": bench.industry,
            "cm_ratio_low": bench.cm_ratio_low,
            "cm_ratio_high": bench.cm_ratio_high,
            "operating_leverage_typical": bench.operating_leverage_typical,
            "note": bench.note,
            "user_cm_ratio": h.cm_ratio,
            "user_position": (
                "below" if h.cm_ratio < bench.cm_ratio_low
                else ("above" if h.cm_ratio > bench.cm_ratio_high else "in_range")
            ),
        }),
        "heatmap": grid,
        "monte_carlo": {
            "n_runs": mc.n_runs,
            "span_pct": mc.span_pct,
            "seed": mc.seed,
            "median_be": mc.median_be,
            "mean_be": mc.mean_be,
            "stdev_be": mc.stdev_be,
            "p5_be": mc.p5_be,
            "p25_be": mc.p25_be,
            "p75_be": mc.p75_be,
            "p95_be": mc.p95_be,
            "pct_undefined": mc.pct_undefined,
            "histogram": mc.histogram,
        },
        "time_phased": [
            {
                "period_label": tp.period_label,
                "units": tp.units,
                "cumulative_units": tp.cumulative_units,
                "cumulative_profit": tp.cumulative_profit,
                "crossed": tp.crossed,
            }
            for tp in cvp.time_phased
        ],
        "first_crossing_period": (
            first_crossing_period(cvp.time_phased) if cvp.time_phased else None
        ),
        "sensitivity": [
            {
                "variable": r.variable,
                "delta_pct": r.delta_pct,
                "new_value": r.new_value,
                "new_break_even_units": r.new_break_even_units,
                "swing_units": r.swing_units,
                "swing_pct": r.swing_pct,
            }
            for r in cvp.sensitivity
        ],
        "tornado": [
            {
                "variable": t.variable,
                "swing_minus_10_pct": t.swing_minus_10_pct,
                "swing_plus_10_pct": t.swing_plus_10_pct,
                "abs_max_swing": t.abs_max_swing,
            }
            for t in cvp.tornado
        ],
        "warnings": list(result.warnings),
        "source_filename": result.source_filename,
        "elapsed_ms": result.elapsed_ms,
        "commentary": {
            "headline": result.commentary.headline,
            "summary": result.commentary.summary,
            "risks": list(result.commentary.risks),
            "actions": list(result.commentary.actions),
            "cost_usd": round(result.commentary.cost_usd, 6),
            "input_tokens": result.commentary.input_tokens,
            "output_tokens": result.commentary.output_tokens,
            "cache_hit_tokens": result.commentary.cache_hit_tokens,
            "model": result.commentary.model,
            "skipped": result.commentary.skipped,
            "error": result.commentary.error,
        },
        "total_cost_usd": round(result.total_cost_usd, 6),
    }


def scenario(*,
             base_inputs: CVPInputs,
             base_metadata: CVPMetadata,
             overrides: dict) -> dict:
    """Recompute headline + sensitivity from a what-if override.

    overrides may contain: price_per_unit, variable_cost_per_unit,
    fixed_cost, target_profit, current_volume. Anything missing falls
    back to the base value. Pure deterministic, no AI.
    """
    new_inp = CVPInputs(
        fixed_cost=float(overrides.get("fixed_cost", base_inputs.fixed_cost)),
        variable_cost_per_unit=float(overrides.get("variable_cost_per_unit",
                                                   base_inputs.variable_cost_per_unit)),
        price_per_unit=float(overrides.get("price_per_unit", base_inputs.price_per_unit)),
        target_profit=overrides.get("target_profit", base_inputs.target_profit),
    )
    new_md = CVPMetadata(
        company=base_metadata.company,
        currency=base_metadata.currency,
        period_label=base_metadata.period_label,
        current_volume=overrides.get("current_volume", base_metadata.current_volume),
        capacity_units=base_metadata.capacity_units,
        non_cash_amount=base_metadata.non_cash_amount,
        industry=base_metadata.industry,
    )
    if new_inp.price_per_unit <= 0 or new_inp.variable_cost_per_unit < 0 \
            or new_inp.fixed_cost < 0:
        return {"error": "Invalid scenario values."}
    h = headline_stats(new_inp, new_md)
    return {
        "inputs": {
            "fixed_cost": new_inp.fixed_cost,
            "variable_cost_per_unit": new_inp.variable_cost_per_unit,
            "price_per_unit": new_inp.price_per_unit,
            "target_profit": new_inp.target_profit,
            "current_volume": new_md.current_volume,
        },
        "headline": {
            "contribution_margin_per_unit": h.contribution_margin_per_unit,
            "cm_ratio": h.cm_ratio,
            "break_even_units": (None if h.break_even_units == float("inf")
                                 else h.break_even_units),
            "break_even_revenue": (None if h.break_even_revenue == float("inf")
                                   else h.break_even_revenue),
            "margin_of_safety_units": h.margin_of_safety_units,
            "margin_of_safety_pct": h.margin_of_safety_pct,
            "target_profit_units": h.target_profit_units,
            "target_profit_revenue": h.target_profit_revenue,
            "operating_leverage_at_current": h.operating_leverage_at_current,
        },
    }


FOLLOWUP_SYSTEM_PROMPT = (
    "You are a CFO already familiar with this company's break-even profile. "
    "The user is asking a follow-up question about it. Answer in two to three "
    "sentences, plain language. Cite specific numbers when useful. Do not "
    "restate the inputs. Speak directly. If the question is out of scope (not "
    "about CVP / pricing / unit economics), say so politely in one sentence."
)


def followup(*, run_payload: dict, question: str,
             model: str | None = None, api_key: str | None = None) -> dict:
    """Answer a free-text question about a cached run.

    run_payload is the same to_dict(result) shape (the cache stores it).
    Returns: {answer, cost_usd, input_tokens, output_tokens, model, error}.
    """
    md = run_payload.get("metadata", {})
    h = run_payload.get("headline", {}) or {}
    inp = run_payload.get("inputs", {}) or {}
    digest_lines = [
        f"Subject: {md.get('company','')}  |  Currency: {md.get('currency','GBP')}",
        f"Inputs: price={inp.get('price_per_unit',0):.2f}  "
        f"vc={inp.get('variable_cost_per_unit',0):.2f}  "
        f"fixed={inp.get('fixed_cost',0):,.0f}",
        f"Headline: BE={h.get('break_even_units')}  "
        f"CM_ratio={h.get('cm_ratio',0):.3f}  "
        f"MoS={h.get('margin_of_safety_units')}  "
        f"OpLev={h.get('operating_leverage_at_current')}",
        "",
        f"User question: {question.strip()[:500]}",
    ]
    digest = "\n".join(digest_lines)
    schema = (
        '{\n'
        '  "answer": "2-3 sentences directly answering the question"\n'
        '}'
    )
    try:
        data, stats = ask_deepseek_json_with_stats(
            digest,
            system=FOLLOWUP_SYSTEM_PROMPT + "\n\nReply schema:\n" + schema,
            max_tokens=300,
            model=(model or DEEPSEEK_MODEL_FAST),
            api_key=api_key,
        )
    except Exception as e:
        return {
            "answer": "",
            "error": _scrub(e),
            "model": model or DEEPSEEK_MODEL_FAST,
            "cost_usd": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
    return {
        "answer": str(data.get("answer") or "").strip(),
        "error": None,
        "model": stats.model,
        "cost_usd": round(stats.cost_usd, 6),
        "input_tokens": stats.input_tokens,
        "output_tokens": stats.output_tokens,
    }


def _scrub(e: Exception) -> str:
    msg = f"{type(e).__name__}: {e}"
    msg = re.sub(r"/[^\s'\"]+|[A-Z]:\\[^\s'\"]+", "<path>", msg)
    msg = re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-***", msg)
    return msg[:300]
