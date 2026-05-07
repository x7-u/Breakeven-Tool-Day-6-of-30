"""Day 6. BREAK. Local Flask server for the Cost-Volume-Profit tool.

Bound to 127.0.0.1:1006 by default. Day-N port = 1000 + N.

Routes:
  GET  /                         renders index.html, sets CSRF cookie
  POST /api/analyse              workbook upload + sample picker, returns CVP JSON
  GET  /api/status               environment + sample availability
  GET  /api/runs                 cost-log entries with cached flag
  GET  /api/runs/<run_id>        re-open a cached run
  GET  /api/download/<filename>  serves a file from outputs/
  POST /api/shutdown             debug-only clean stop
  GET  /favicon.ico              static SVG icon
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import secrets
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks import INDUSTRY_BENCHMARKS, all_industries
from cost_log import CostLog
from cvp_csv import write_csv
from cvp_excel import write_workbook
from cvp_schema import CVPInputs, CVPMetadata
from flask import Flask, abort, jsonify, make_response, render_template, request, send_file
from monte_carlo import simulate as mc_simulate
from pipeline import analyse, estimate_cost, followup, scenario, to_dict
from run_cache import RunCache
from werkzeug.utils import safe_join, secure_filename

from shared.config import DEEPSEEK_API_KEY

HERE = Path(__file__).resolve().parent
SAMPLE_DIR = HERE / "sample_data"
OUTPUTS = HERE / "outputs"
UPLOADS = HERE / "uploads"
LOGS = HERE / "logs"

SAMPLES: dict[str, dict] = {
    "coffee_shop": {
        "filename": "sample_coffee_shop.xlsx",
        "label": "Pour & Roast Coffee (GBP). Low fixed, low price, high volume. Tight per-cup margin; volume is everything.",
    },
    "low_cost_airline": {
        "filename": "sample_low_cost_airline.xlsx",
        "label": "SkyHopper Airways (EUR). Huge fixed (fleet + slots), thin per-seat margin. Massive operating leverage.",
    },
    "software_saas": {
        "filename": "sample_software_saas.xlsx",
        "label": "Ledgerly SaaS (USD). High fixed (engineers + hosting), fat per-seat margin. Fixed cost is the only lever.",
    },
    "brew_and_bites": {
        "filename": "sample_brew_and_bites.xlsx",
        "label": "Brew & Bites Cafe (GBP). Multi-product (drinks, food, retail) + step-cost ladder for second barista.",
    },
}

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXTS = {".xlsx"}
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"

app = Flask(
    __name__,
    template_folder=str(HERE / "templates"),
    static_folder=str(HERE / "static"),
)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

_analyse_lock = threading.Lock()
_cost_log = CostLog(OUTPUTS / "runs.jsonl")
_run_cache = RunCache(OUTPUTS / "runs")


# ---- Logging ---------------------------------------------------------

LOGS.mkdir(parents=True, exist_ok=True)
_handler = logging.handlers.RotatingFileHandler(
    LOGS / "server.log", maxBytes=512_000, backupCount=3, encoding="utf-8",
)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler, logging.StreamHandler()])
log = logging.getLogger("day06.server")


# ---- Helpers ---------------------------------------------------------

def _env_key_ok() -> bool:
    return bool(DEEPSEEK_API_KEY) and not DEEPSEEK_API_KEY.startswith("sk-placeholder")


def _ensure_csrf_cookie(resp):
    if not request.cookies.get(CSRF_COOKIE_NAME):
        resp.set_cookie(
            CSRF_COOKIE_NAME, secrets.token_urlsafe(24),
            samesite="Strict", httponly=False, secure=False, max_age=24 * 3600,
        )
    return resp


def _csrf_check() -> bool:
    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    header = request.headers.get(CSRF_HEADER_NAME, "")
    return bool(cookie) and secrets.compare_digest(cookie, header)


def _samples_for_template():
    out = []
    for sid, meta in SAMPLES.items():
        if (SAMPLE_DIR / meta["filename"]).exists():
            out.append({"id": sid, "filename": meta["filename"], "label": meta["label"]})
    return out


def _cost_log_dict() -> dict:
    s = _cost_log.summary()
    return {
        "runs": s.runs,
        "cost_usd_total": s.cost_usd_total,
        "rows_total": s.rows_total,
        "last_run_at": s.last_run_at,
        "cost_usd_30d": s.cost_usd_30d,
        "runs_30d": s.runs_30d,
    }


def _guardrail_usd() -> float:
    return float(os.getenv("DAY06_MAX_COST_USD", "0.05"))


# ---- Routes ----------------------------------------------------------

@app.route("/")
def index():
    resp = make_response(render_template(
        "index.html",
        env_key_ok=_env_key_ok(),
        samples=_samples_for_template(),
        max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
    ))
    return _ensure_csrf_cookie(resp)


@app.route("/api/status")
def status():
    return jsonify(
        env_key_ok=_env_key_ok(),
        samples=_samples_for_template(),
        max_upload_mb=MAX_UPLOAD_BYTES // (1024 * 1024),
        cost_log=_cost_log_dict(),
        guardrail_usd=round(_guardrail_usd(), 6),
        estimated_cost_usd=round(estimate_cost(), 6),
    )


@app.route("/api/runs")
def runs_list():
    entries = _cost_log.entries(limit=200)
    out = []
    for e in entries:
        eid = e.get("id")
        cached = bool(eid) and (_run_cache.root / f"{eid}.json").is_file()
        out.append({**e, "cached": cached})
    return jsonify(entries=out, summary=_cost_log_dict())


@app.route("/api/runs/<run_id>")
def run_get(run_id: str):
    if not run_id or len(run_id) > 64 or not run_id.replace("-", "").isalnum():
        return jsonify(error="Invalid run id."), 400
    payload = _run_cache.get(run_id)
    if payload is None:
        return jsonify(error="Run not cached."), 404
    return jsonify(payload)


@app.route("/api/analyse", methods=["POST"])
def api_analyse():
    if not _csrf_check():
        return jsonify(error="CSRF token missing or invalid. Refresh the page."), 403
    if not _analyse_lock.acquire(blocking=False):
        return jsonify(error="Another analysis is already in flight. Wait for it to finish."), 429

    started = time.time()
    try:
        use_samples = request.form.get("use_samples") == "true"
        sample_id = (request.form.get("sample_id") or "").strip()
        skip_ai = request.form.get("skip_ai") == "true"
        api_key_override = (request.form.get("api_key") or "").strip() or None
        model_choice = (request.form.get("model") or "").strip() or None

        file_bytes: bytes | None = None
        display_name = ""

        if use_samples:
            if sample_id not in SAMPLES:
                return jsonify(error=f"Unknown sample id: '{sample_id}'."), 400
            fname = SAMPLES[sample_id]["filename"]
            sample_path = SAMPLE_DIR / fname
            if not sample_path.exists():
                return jsonify(error=f"Sample file missing on disk: {fname}."), 500
            file_bytes = sample_path.read_bytes()
            display_name = fname
        else:
            upload = request.files.get("file")
            if upload is None or not upload.filename:
                return jsonify(error="No file uploaded. Pick an .xlsx workbook."), 400
            safe_name = secure_filename(upload.filename) or "upload.xlsx"
            ext = Path(safe_name).suffix.lower()
            if ext not in ALLOWED_EXTS:
                return jsonify(error=f"Unsupported file type: {ext} (only .xlsx is supported)."), 400
            file_bytes = upload.read()
            UPLOADS.mkdir(parents=True, exist_ok=True)
            (UPLOADS / f"{uuid.uuid4().hex[:8]}_{safe_name}").write_bytes(file_bytes)
            display_name = safe_name

        try:
            result = analyse(
                file_bytes=file_bytes, source_filename=display_name,
                skip_ai=skip_ai, model=model_choice, api_key=api_key_override,
            )
        except ValueError as e:
            log.warning("analyse validation error: %s", e)
            return jsonify(error=str(e)), 400

        # Write outputs (filename slug includes company + period + timestamp)
        slug = _slug(result.cvp.metadata.company, result.cvp.metadata.period_label)
        ts = time.strftime("%Y%m%d-%H%M")
        xlsx_path = OUTPUTS / f"break_{slug}_{ts}.xlsx"
        csv_path = OUTPUTS / f"break_{slug}_{ts}_sensitivity.csv"
        write_workbook(result.cvp, xlsx_path)
        write_csv(result.cvp, csv_path)

        # Optional PPTX/PDF if available
        pptx_name: str | None = None
        pdf_name: str | None = None
        try:
            from break_pptx import is_available as _pptx_avail
            from break_pptx import write_pptx
            if _pptx_avail():
                pptx_path = OUTPUTS / f"break_{slug}_{ts}.pptx"
                write_pptx(result, pptx_path)
                pptx_name = pptx_path.name
        except Exception:
            log.exception("pptx write failed")
        try:
            from break_pdf import write_pdf
            pdf_path = OUTPUTS / f"break_{slug}_{ts}.pdf"
            write_pdf(result, pdf_path)
            pdf_name = pdf_path.name
        except Exception:
            log.exception("pdf write failed")

        elapsed_ms = int((time.time() - started) * 1000)
        ai_cost = result.total_cost_usd
        log_entry = _cost_log.append(
            company=result.cvp.metadata.company,
            period_label=result.cvp.metadata.period_label,
            rows=len(result.cvp.sensitivity),
            cost_usd=ai_cost,
            model=result.commentary.model or "(deterministic)",
            skipped=bool(result.commentary.skipped),
            elapsed_ms=elapsed_ms,
            source_filename=display_name,
            total_variance=result.cvp.headline.cm_ratio,
            total_variance_pct=None,
            rag_red=0,
        )
        log.info(
            "analyse OK company=%s be_units=%s ms=%d cost_usd=%.6f",
            result.cvp.metadata.company,
            ("inf" if result.cvp.headline.break_even_units == float("inf")
             else f"{result.cvp.headline.break_even_units:.0f}"),
            elapsed_ms, ai_cost,
        )

        body = to_dict(result)
        body.update(
            xlsx_filename=xlsx_path.name,
            csv_filename=csv_path.name,
            pptx_filename=pptx_name,
            pdf_filename=pdf_name,
            elapsed_ms=elapsed_ms,
            cost_log=_cost_log_dict(),
            run_id=log_entry["id"],
        )
        try:
            _run_cache.save(log_entry["id"], body)
        except Exception:
            log.exception("failed to cache run %s", log_entry["id"])
        return jsonify(body)
    except Exception:
        log.exception("analyse unexpected error")
        return jsonify(
            error="Server error during analysis. See logs/server.log for details."
        ), 500
    finally:
        _analyse_lock.release()


@app.route("/api/scenario", methods=["POST"])
def api_scenario():
    """Recompute headline + CM for a what-if override. No AI call."""
    if not _csrf_check():
        return jsonify(error="CSRF token missing or invalid."), 403
    f = request.form
    base_inp = CVPInputs(
        fixed_cost=float(f.get("fixed_cost", "0")),
        variable_cost_per_unit=float(f.get("variable_cost_per_unit", "0")),
        price_per_unit=float(f.get("price_per_unit", "1")),
        target_profit=(float(f.get("target_profit")) if f.get("target_profit")
                       not in (None, "") else None),
    )
    base_md = CVPMetadata(
        company=f.get("company", ""),
        currency=f.get("currency", "GBP"),
        period_label=f.get("period_label", ""),
        current_volume=(float(f.get("current_volume")) if f.get("current_volume")
                        not in (None, "") else None),
    )
    overrides_json = f.get("overrides", "{}")
    try:
        import json as _json
        overrides = _json.loads(overrides_json)
    except Exception:
        return jsonify(error="overrides must be a JSON object."), 400
    try:
        return jsonify(scenario(
            base_inputs=base_inp, base_metadata=base_md, overrides=overrides,
        ))
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400


@app.route("/api/followup", methods=["POST"])
def api_followup():
    """Free-text follow-up question against a cached run. One DeepSeek call."""
    if not _csrf_check():
        return jsonify(error="CSRF token missing or invalid."), 403
    run_id = (request.form.get("run_id") or "").strip()
    question = (request.form.get("question") or "").strip()
    if not run_id or not question:
        return jsonify(error="run_id and question are required."), 400
    payload = _run_cache.get(run_id)
    if payload is None:
        return jsonify(error="Run not in cache. Re-run the analysis first."), 404
    api_key = (request.form.get("api_key") or "").strip() or None
    model = (request.form.get("model") or "").strip() or None
    return jsonify(followup(
        run_payload=payload, question=question,
        model=model, api_key=api_key,
    ))


@app.route("/api/compare", methods=["POST"])
def api_compare():
    """Compare two cached runs by run_id; return key deltas."""
    if not _csrf_check():
        return jsonify(error="CSRF token missing or invalid."), 403
    a_id = (request.form.get("a") or "").strip()
    b_id = (request.form.get("b") or "").strip()
    if not (a_id and b_id):
        return jsonify(error="Provide both run ids (a and b)."), 400
    a = _run_cache.get(a_id)
    b = _run_cache.get(b_id)
    if a is None or b is None:
        return jsonify(error="One or both runs not cached."), 404

    def _h(d, k):
        return ((d.get("headline") or {}).get(k))
    keys = [
        "break_even_units", "break_even_revenue",
        "cm_ratio", "contribution_margin_per_unit",
        "margin_of_safety_units", "margin_of_safety_pct",
        "target_profit_units", "operating_leverage_at_current",
        "cash_break_even_units",
    ]
    deltas = {}
    for k in keys:
        av = _h(a, k)
        bv = _h(b, k)
        if av is None or bv is None:
            deltas[k] = {"a": av, "b": bv, "delta": None, "delta_pct": None}
        else:
            d = bv - av
            dp = (d / av) if av else None
            deltas[k] = {"a": av, "b": bv, "delta": d, "delta_pct": dp}
    return jsonify(
        a_id=a_id, b_id=b_id,
        a_company=(a.get("metadata") or {}).get("company"),
        b_company=(b.get("metadata") or {}).get("company"),
        deltas=deltas,
    )


@app.route("/api/runs/<run_id>/save", methods=["POST"])
def api_run_save(run_id: str):
    """Add or update a label on a cached run for easy re-open."""
    if not _csrf_check():
        return jsonify(error="CSRF token missing or invalid."), 403
    if not run_id or len(run_id) > 64 or not run_id.replace("-", "").isalnum():
        return jsonify(error="Invalid run id."), 400
    label = (request.form.get("label") or "").strip()[:80]
    payload = _run_cache.get(run_id)
    if payload is None:
        return jsonify(error="Run not cached."), 404
    payload["label"] = label
    try:
        _run_cache.save(run_id, payload)
    except Exception:
        log.exception("failed to save label on run %s", run_id)
        return jsonify(error="Could not save label."), 500
    return jsonify(saved=True, run_id=run_id, label=label)


@app.route("/api/montecarlo", methods=["POST"])
def api_montecarlo():
    """Re-run Monte Carlo with tunable params. No AI."""
    if not _csrf_check():
        return jsonify(error="CSRF token missing or invalid."), 403
    f = request.form
    try:
        inp = CVPInputs(
            fixed_cost=float(f.get("fixed_cost", "0")),
            variable_cost_per_unit=float(f.get("variable_cost_per_unit", "0")),
            price_per_unit=float(f.get("price_per_unit", "1")),
        )
        n_runs = max(100, min(20_000, int(f.get("n_runs", "4000"))))
        span = max(0.01, min(1.0, float(f.get("span_pct", "0.20"))))
        seed = int(f.get("seed", "42"))
    except (ValueError, TypeError) as e:
        return jsonify(error=f"Invalid Monte Carlo params: {e}"), 400
    mc = mc_simulate(inp, n_runs=n_runs, span_pct=span, seed=seed)
    return jsonify(
        n_runs=mc.n_runs, span_pct=mc.span_pct, seed=mc.seed,
        median_be=mc.median_be, mean_be=mc.mean_be, stdev_be=mc.stdev_be,
        p5_be=mc.p5_be, p25_be=mc.p25_be, p75_be=mc.p75_be, p95_be=mc.p95_be,
        pct_undefined=mc.pct_undefined,
        histogram=mc.histogram,
    )


@app.route("/api/benchmarks")
def api_benchmarks():
    """Return the industry benchmark dictionary so the UI can populate a list."""
    out = []
    seen: set[str] = set()
    for v in INDUSTRY_BENCHMARKS.values():
        if v.industry in seen:
            continue
        seen.add(v.industry)
        out.append({
            "industry": v.industry,
            "cm_ratio_low": v.cm_ratio_low,
            "cm_ratio_high": v.cm_ratio_high,
            "operating_leverage_typical": v.operating_leverage_typical,
            "note": v.note,
        })
    return jsonify(industries=out, names=all_industries())


@app.errorhandler(413)
def _too_large(_e):
    return jsonify(error=f"Upload exceeds {MAX_UPLOAD_BYTES // 1024 // 1024} MB limit."), 413


@app.route("/api/download/<path:filename>")
def download(filename: str):
    safe = secure_filename(filename) or ""
    if not safe:
        abort(400)
    full = safe_join(str(OUTPUTS), safe)
    if not full or not Path(full).is_file():
        return jsonify(error=f"Not found: {safe}"), 404
    return send_file(full, as_attachment=True, download_name=safe)


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    if not (app.debug or os.getenv("DAY06_ALLOW_SHUTDOWN") == "1"):
        return jsonify(error="Shutdown not enabled."), 403
    if not _csrf_check():
        return jsonify(error="CSRF token missing."), 403
    threading.Thread(target=lambda: (time.sleep(0.2), os._exit(0)), daemon=True).start()
    return jsonify(stopped=True)


@app.route("/favicon.ico")
def favicon():
    p = HERE / "static" / "favicon.svg"
    if p.exists():
        return send_file(p)
    return ("", 204)


def _slug(company: str, period: str) -> str:
    out = []
    for ch in f"{company}_{period}".lower():
        out.append(ch if ch.isalnum() else "_")
    s = "".join(out).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s[:48] or "run"


# ---- CLI -------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("DAY06_PORT", "1006")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    print()
    print("  Day 6. BREAK . Cost-Volume-Profit Tool")
    print(f"  Local URL:  http://{args.host}:{args.port}/")
    print("  Press Ctrl+C to stop.")
    print()
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=args.debug)


if __name__ == "__main__":
    main()
