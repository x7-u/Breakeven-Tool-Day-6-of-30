// Day 6 BREAK front-end. CSRF double-submit, single AbortController per run,
// SVG render done client-side from the JSON payload. Live what-if + heatmap +
// multi-product + step-cost + benchmark + capacity + cash + save/compare +
// follow-up + show-the-working + URL state + print.

(() => {
  "use strict";

  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---- DOM refs ----
  const form        = $("#analyse-form");
  const btn         = $("#run-btn");
  const statusLine  = $("#status-line");
  const errorCard   = $("#error-card");
  const empty       = $("#empty-state");
  const resultPane  = $("#result-pane");
  const hero        = $("#hero");
  const aiCard      = $("#ai-card");
  const chartCard   = $("#chart-card");
  const chartHost   = $("#chart-host");
  const sensCard    = $("#sens-card");
  const sensTable   = $("#sens-table");
  const dlBlock     = $("#downloads");
  const sampleCard  = $("#sample-card");
  const uploadCard  = $("#upload-card");
  const capCard     = $("#capacity-card");
  const whatifCard  = $("#whatif-card");
  const targetsCard = $("#targets-card");
  const comp3Card   = $("#comp3-card");
  const multiCard   = $("#multi-card");
  const stepCard    = $("#step-card");
  const heatCard    = $("#heat-card");
  const workCard    = $("#working-card");
  const compareCard = $("#compare-card");
  const savedBlock  = $("#saved-runs-block");
  const savedList   = $("#saved-list");
  const covCard     = $("#covenant-card");
  const mcCard      = $("#mc-card");
  const timeCard    = $("#time-card");

  let inflight  = null;
  let lastBody  = null;     // most recent /api/analyse payload
  let savedRuns = loadSaved();

  // ---- Cookie / utils ----
  function readCookie(name) {
    return document.cookie.split(/;\s*/)
      .map(p => p.split("="))
      .reduce((a, [k, v]) => (k === name ? decodeURIComponent(v || "") : a), "");
  }
  function csrfHeaders() { return { "X-CSRF-Token": readCookie("csrf_token") }; }

  function setStatus(msg, kind) {
    statusLine.textContent = msg || "";
    statusLine.style.color = kind === "error" ? "#991B1B"
                          : kind === "ok"     ? "#065F46" : "";
  }
  function show(el) { if (el) el.classList.remove("hidden"); }
  function hide(el) { if (el) el.classList.add("hidden"); }

  function fmtNum(x, digits = 0) {
    if (x === null || x === undefined || !isFinite(x)) return "n/a";
    return Number(x).toLocaleString(undefined, {
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    });
  }
  function fmtCcy(x, ccy, digits = 0) {
    if (x === null || x === undefined || !isFinite(x)) return "n/a";
    const sym = { GBP: "£", USD: "$", EUR: "€" }[ccy] || "";
    return sym + fmtNum(x, digits);
  }
  function fmtPct(x, digits = 2) {
    if (x === null || x === undefined || !isFinite(x)) return "n/a";
    return (x * 100).toFixed(digits) + "%";
  }

  // ---- Source toggle ----
  $$('input[name="source"]').forEach(r => {
    r.addEventListener("change", () => {
      const v = r.checked ? r.value : null;
      if (!v) return;
      if (v === "samples") { show(sampleCard); hide(uploadCard); }
      else                 { hide(sampleCard); show(uploadCard); }
    });
  });

  // ---- Submit (analyse) ----
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (inflight) inflight.abort();
    inflight = new AbortController();
    btn.disabled = true;
    setStatus("Crunching the maths and asking the AI...");
    hide(errorCard);

    const fd = new FormData();
    const source = $('input[name="source"]:checked').value;
    if (source === "samples") {
      fd.append("use_samples", "true");
      fd.append("sample_id", $("#sample-select").value);
    } else {
      const file = $("#file-input").files[0];
      if (!file) {
        setStatus("Pick an .xlsx file first.", "error");
        btn.disabled = false;
        return;
      }
      fd.append("file", file);
    }
    if ($("#skip-ai").checked) fd.append("skip_ai", "true");
    const model = $("#model").value.trim();
    if (model) fd.append("model", model);

    try {
      const res = await fetch("/api/analyse", {
        method: "POST", body: fd,
        headers: csrfHeaders(), signal: inflight.signal,
      });
      const body = await res.json();
      if (!res.ok) { showError(body.error || `HTTP ${res.status}`); return; }
      lastBody = body;
      render(body);
      try { localStorage.setItem("day06.lastResult.v1", JSON.stringify(body)); } catch (_) {}
      setStatus(`DONE IN ${body.elapsed_ms}MS / AI COST $${(body.total_cost_usd || 0).toFixed(5)}`, "ok");
    } catch (e) {
      if (e.name === "AbortError") return;
      showError(e.message || String(e));
    } finally {
      btn.disabled = false;
    }
  });

  function showError(msg) {
    errorCard.textContent = msg;
    show(errorCard);
    setStatus("FAILED", "error");
  }

  // ---- Count-up ramp for the hero ----
  function rampTo(el, finalNum, ms = 700) {
    if (!isFinite(finalNum)) { el.textContent = "n/a"; return; }
    const start = performance.now();
    function tick(now) {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = fmtNum(finalNum * eased);
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ---- MAIN render ----
  function render(body) {
    const md = body.metadata || {};
    const inp = body.inputs || {};
    const h = body.headline || {};
    const ccy = md.currency || "GBP";

    // Run-meta
    $("#run-company").textContent  = md.company || "--";
    $("#run-period").textContent   = md.period_label || "--";
    $("#run-currency").textContent = ccy;
    $("#run-id").textContent       = body.run_id || "--";

    // ---- Hero ----
    if (h.break_even_units !== null && isFinite(h.break_even_units)) {
      rampTo($("#hero-be"), h.break_even_units);
    } else {
      $("#hero-be").textContent = "NEVER";
    }
    $("#hero-be-rev").textContent = h.break_even_revenue !== null
      ? fmtCcy(h.break_even_revenue, ccy) + " revenue"
      : "no positive contribution margin";
    $("#hero-cm").textContent  = fmtPct(h.cm_ratio);
    $("#hero-cm-per-unit").textContent =
      fmtCcy(h.contribution_margin_per_unit, ccy, 2) + " per unit";

    if (h.margin_of_safety_units !== null) {
      $("#hero-mos").textContent = fmtNum(h.margin_of_safety_units) + "u";
      $("#hero-mos-foot").textContent =
        (h.margin_of_safety_pct === null ? "" : fmtPct(h.margin_of_safety_pct ?? 0) + " ") +
        "vs current volume";
    } else {
      $("#hero-mos").textContent = "n/a";
      $("#hero-mos-foot").textContent = "no current volume";
    }
    $("#hero-cost").textContent = "$" + (body.total_cost_usd || 0).toFixed(5);
    $("#hero-elapsed").textContent = (body.elapsed_ms || 0) + " ms total";
    show(hero);

    // ---- Cash basis toggle ----
    if (h.cash_break_even_units !== null && h.cash_break_even_units !== undefined) {
      show($("#cash-toggle-wrap"));
      const cb = $("#cash-toggle");
      cb.checked = false;
      cb.onchange = () => {
        const target = cb.checked ? h.cash_break_even_units : h.break_even_units;
        rampTo($("#hero-be"), target, 350);
        $("#hero-be-rev").textContent = cb.checked
          ? fmtCcy(target * (inp.price_per_unit || 0), ccy) + " revenue (cash basis)"
          : (h.break_even_revenue !== null
             ? fmtCcy(h.break_even_revenue, ccy) + " revenue"
             : "n/a");
      };
    } else {
      hide($("#cash-toggle-wrap"));
    }

    // ---- Benchmark band ----
    const bench = body.benchmark;
    if (bench) {
      show($("#bench-bar"));
      const lo = bench.cm_ratio_low, hi = bench.cm_ratio_high;
      const vmin = Math.min(lo - 0.05, h.cm_ratio - 0.02, 0);
      const vmax = Math.max(hi + 0.05, h.cm_ratio + 0.02, 1);
      const range = vmax - vmin;
      const pct = (x) => ((x - vmin) / range * 100).toFixed(1) + "%";
      $("#bench-band").style.left  = pct(lo);
      $("#bench-band").style.width = ((hi - lo) / range * 100).toFixed(1) + "%";
      $("#bench-marker").style.left = pct(h.cm_ratio);
      const posCls = bench.user_position === "in_range" ? "pos-in"
                   : bench.user_position === "below"   ? "pos-below" : "pos-above";
      $("#bench-meta").innerHTML =
        `${bench.industry}: peers ${fmtPct(lo,0)} to ${fmtPct(hi,0)} - you are ` +
        `<span class="${posCls}">${bench.user_position.replace("_", " ")}</span>`;
    } else {
      hide($("#bench-bar"));
    }

    // ---- Capacity card ----
    if (h.capacity_units) {
      show(capCard);
      const reach = h.capacity_reachable;
      $("#cap-pill").textContent = reach ? "REACHABLE" : "NOT REACHABLE";
      $("#cap-pill").classList.toggle("is-warn", !reach);
      const buf = (h.capacity_buffer_pct ?? 0);
      $("#cap-text").textContent =
        `Capacity ceiling ${fmtNum(h.capacity_units)} units. ` +
        (reach
          ? `BE at ${fmtNum(h.break_even_units)}u sits ${fmtPct(buf, 1)} below ceiling.`
          : `BE at ${fmtNum(h.break_even_units)}u exceeds ceiling.`);
    } else {
      hide(capCard);
    }

    // ---- AI verdict ----
    const c = body.commentary || {};
    if (!c.skipped && (c.headline || c.summary)) {
      $("#ai-headline").textContent = c.headline || "";
      $("#ai-summary").textContent = c.summary || "";
      const r = $("#ai-risks"), a = $("#ai-actions");
      r.innerHTML = ""; a.innerHTML = "";
      (c.risks || []).forEach(x => { const li = document.createElement("li"); li.textContent = x; r.appendChild(li); });
      (c.actions || []).forEach(x => { const li = document.createElement("li"); li.textContent = x; a.appendChild(li); });
      show(aiCard);
      $("#followup-answer").hidden = true;
      $("#followup-status").textContent = "";
    } else {
      hide(aiCard);
    }

    // ---- Chart ----
    chartHost.innerHTML = renderBreakEvenSVG(inp, h, md.current_volume, md.capacity_units);
    if (md.capacity_units) show($("#lg-capacity")); else hide($("#lg-capacity"));
    show(chartCard);

    // ---- What-if sliders ----
    setupSliders(inp, md);
    show(whatifCard);

    // ---- Targets calculator ----
    setupTargets(inp, md, ccy);
    show(targetsCard);

    // ---- Compare three prices ----
    setupCompare3(inp, md, ccy);
    show(comp3Card);

    // ---- Multi-product ----
    if (body.multi_product) {
      renderMulti(body.multi_product, ccy, inp);
      setupMixSliders(body.multi_product, inp, ccy);
      show(multiCard);
    } else {
      hide(multiCard);
    }

    // ---- Covenant ----
    if (h.covenant_min_revenue) {
      show(covCard);
      const breach = h.covenant_breach;
      $("#cov-pill").textContent = breach ? "COVENANT BREACH" : "COVENANT OK";
      $("#cov-pill").classList.toggle("is-warn", !!breach);
      const buf = h.covenant_buffer_pct;
      $("#cov-text").textContent =
        `Min revenue covenant ${fmtCcy(h.covenant_min_revenue, ccy)} per period. ` +
        (buf === null || buf === undefined
          ? "No current volume to compare."
          : `Current sits ${fmtPct(buf, 1)} ${buf >= 0 ? "above" : "below"} the floor.`);
    } else {
      hide(covCard);
    }

    // ---- Monte Carlo ----
    if (body.monte_carlo) {
      renderMonteCarlo(body.monte_carlo);
      show(mcCard);
    } else {
      hide(mcCard);
    }

    // ---- Time-phased BE ----
    if (body.time_phased && body.time_phased.length) {
      renderTimePhased(body.time_phased, body.first_crossing_period, ccy);
      show(timeCard);
    } else {
      hide(timeCard);
    }

    // ---- Step-cost ----
    if (body.step_cost_be && body.step_cost_be.length > 1) {
      renderStep(body.step_cost_be, ccy);
      show(stepCard);
    } else {
      hide(stepCard);
    }

    // ---- Sensitivity ----
    sensTable.innerHTML = renderSensTable(body.sensitivity, ccy);
    show(sensCard);

    // ---- Heatmap ----
    if (body.heatmap) {
      $("#heat-host").innerHTML = renderHeatmap(body.heatmap, ccy);
      show(heatCard);
    } else {
      hide(heatCard);
    }

    // ---- Show-the-working ----
    $("#working-body").innerHTML = renderWorking(inp, h, ccy, body);
    show(workCard);

    // ---- Downloads ----
    setDownload("dl-xlsx", body.xlsx_filename);
    setDownload("dl-csv",  body.csv_filename);
    setDownload("dl-pdf",  body.pdf_filename);
    setDownload("dl-pptx", body.pptx_filename);
    show(dlBlock);

    // ---- URL state (shareable scenario) ----
    syncURL(inp, md);

    hide(empty);
    show(resultPane);
    refreshSavedList();
  }

  function setDownload(id, fname) {
    const a = $("#" + id);
    if (fname) {
      a.href = "/api/download/" + encodeURIComponent(fname);
      a.classList.remove("hidden");
    } else {
      a.classList.add("hidden");
    }
  }

  // ---- Inline SVG break-even chart ----
  function renderBreakEvenSVG(inp, h, currentVolume, capacityUnits) {
    const w = 920, ht = 320, pad = 40;
    const cm = inp.price_per_unit - inp.variable_cost_per_unit;
    const be = cm > 0 ? inp.fixed_cost / cm : 0;
    const maxX = Math.max(be * 2, currentVolume || 0, capacityUnits || 0, 1);
    const revAtMax = inp.price_per_unit * maxX;
    const costAtMax = inp.fixed_cost + inp.variable_cost_per_unit * maxX;
    const maxY = Math.max(revAtMax, costAtMax, 1);
    const innerW = w - 2 * pad, innerH = ht - 2 * pad;
    const xAt = v => pad + (v / maxX) * innerW;
    const yAt = v => pad + (1 - v / maxY) * innerH;
    const purple = "#7C3AED", magenta = "#EC4899", ink = "#0F1117",
          grey = "#6B7280", green = "#10B981", red = "#EF4444";
    const parts = [];
    parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${ht}" width="100%" height="${ht}">`);
    parts.push(`<rect x="${pad}" y="${pad}" width="${innerW}" height="${innerH}" fill="none" stroke="${ink}" stroke-width="1.2"/>`);
    if (cm > 0 && be > 0 && be < maxX) {
      parts.push(`<polygon points="${xAt(0).toFixed(1)},${yAt(0).toFixed(1)} ${xAt(be).toFixed(1)},${yAt(be * inp.price_per_unit).toFixed(1)} ${xAt(0).toFixed(1)},${yAt(inp.fixed_cost).toFixed(1)}" fill="${red}" opacity="0.10"/>`);
      parts.push(`<polygon points="${xAt(be).toFixed(1)},${yAt(be * inp.price_per_unit).toFixed(1)} ${xAt(maxX).toFixed(1)},${yAt(revAtMax).toFixed(1)} ${xAt(maxX).toFixed(1)},${yAt(costAtMax).toFixed(1)}" fill="${green}" opacity="0.10"/>`);
    }
    parts.push(`<line x1="${xAt(0).toFixed(1)}" y1="${yAt(0).toFixed(1)}" x2="${xAt(maxX).toFixed(1)}" y2="${yAt(revAtMax).toFixed(1)}" stroke="${purple}" stroke-width="2.6"/>`);
    parts.push(`<line x1="${xAt(0).toFixed(1)}" y1="${yAt(inp.fixed_cost).toFixed(1)}" x2="${xAt(maxX).toFixed(1)}" y2="${yAt(costAtMax).toFixed(1)}" stroke="${ink}" stroke-width="2.0"/>`);
    parts.push(`<line x1="${xAt(0).toFixed(1)}" y1="${yAt(inp.fixed_cost).toFixed(1)}" x2="${xAt(maxX).toFixed(1)}" y2="${yAt(inp.fixed_cost).toFixed(1)}" stroke="${grey}" stroke-width="1.0" stroke-dasharray="4 4"/>`);
    if (cm > 0 && be > 0) {
      parts.push(`<line x1="${xAt(be).toFixed(1)}" y1="${pad}" x2="${xAt(be).toFixed(1)}" y2="${pad + innerH}" stroke="${magenta}" stroke-width="1.0" stroke-dasharray="2 4"/>`);
      parts.push(`<circle cx="${xAt(be).toFixed(1)}" cy="${yAt(be * inp.price_per_unit).toFixed(1)}" r="7" fill="${magenta}" stroke="${ink}" stroke-width="1.5"/>`);
      parts.push(`<text x="${xAt(be).toFixed(1)}" y="${(pad + innerH + 16).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="10" font-weight="700" fill="${ink}" text-anchor="middle">BE ${Math.round(be).toLocaleString()}u</text>`);
    }
    if (currentVolume) {
      parts.push(`<line x1="${xAt(currentVolume).toFixed(1)}" y1="${pad}" x2="${xAt(currentVolume).toFixed(1)}" y2="${pad + innerH}" stroke="${grey}" stroke-width="0.8" stroke-dasharray="1 3"/>`);
      parts.push(`<text x="${xAt(currentVolume).toFixed(1)}" y="${(pad - 6).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9.5" font-weight="600" fill="${grey}" text-anchor="middle">TODAY ${Math.round(currentVolume).toLocaleString()}u</text>`);
    }
    if (capacityUnits) {
      parts.push(`<line x1="${xAt(capacityUnits).toFixed(1)}" y1="${pad}" x2="${xAt(capacityUnits).toFixed(1)}" y2="${pad + innerH}" stroke="${magenta}" stroke-width="1.4" stroke-dasharray="6 6"/>`);
      parts.push(`<text x="${xAt(capacityUnits).toFixed(1)}" y="${(pad + 12).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9.5" font-weight="700" fill="${magenta}" text-anchor="middle">CAP ${Math.round(capacityUnits).toLocaleString()}u</text>`);
    }
    parts.push(`<text x="${xAt(0).toFixed(1)}" y="${(pad + innerH + 30).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9" fill="${grey}" text-anchor="start">0</text>`);
    parts.push(`<text x="${xAt(maxX).toFixed(1)}" y="${(pad + innerH + 30).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9" fill="${grey}" text-anchor="end">${Math.round(maxX).toLocaleString()}u</text>`);
    parts.push(`</svg>`);
    return parts.join("");
  }

  // ---- Sensitivity table ----
  function renderSensTable(rows, ccy) {
    const pretty = {
      price_per_unit: "Price per unit",
      variable_cost_per_unit: "Variable cost / unit",
      fixed_cost: "Fixed cost",
    };
    let html = `<thead><tr>
      <th>Variable</th><th>Delta</th><th>New value</th>
      <th>New BE</th><th>Swing</th><th>Swing %</th>
    </tr></thead><tbody>`;
    let lastVar = null;
    rows.forEach(r => {
      const cls = [];
      if (r.delta_pct === 0) cls.push("baseline");
      if (lastVar !== null && r.variable !== lastVar) cls.push("var-break");
      lastVar = r.variable;
      const swingCls = r.swing_units === null ? ""
        : (r.swing_units > 0 ? "swing-pos" : (r.swing_units < 0 ? "swing-neg" : ""));
      html += `<tr class="${cls.join(" ")}">
        <td>${pretty[r.variable] || r.variable}</td>
        <td>${(r.delta_pct * 100).toFixed(0)}%</td>
        <td>${fmtCcy(r.new_value, ccy, 2)}</td>
        <td>${r.new_break_even_units === null ? "n/a" : fmtNum(r.new_break_even_units)}</td>
        <td class="${swingCls}">${r.swing_units === null ? "n/a"
          : (r.swing_units > 0 ? "+" : "") + fmtNum(r.swing_units)}</td>
        <td class="${swingCls}">${r.swing_pct === null ? "n/a"
          : (r.swing_pct > 0 ? "+" : "") + fmtPct(r.swing_pct)}</td>
      </tr>`;
    });
    html += "</tbody>";
    return html;
  }

  // ---- Multi-product table ----
  function renderMulti(mp, ccy, _inp) {
    const sum = $("#multi-summary");
    sum.innerHTML =
      `<span><span class="k">WEIGHTED PRICE</span><span class="v">${fmtCcy(mp.weighted_price, ccy, 2)}</span></span>` +
      `<span><span class="k">WEIGHTED VC</span><span class="v">${fmtCcy(mp.weighted_variable_cost, ccy, 2)}</span></span>` +
      `<span><span class="k">WEIGHTED CM</span><span class="v">${fmtCcy(mp.weighted_cm_per_unit, ccy, 2)} (${fmtPct(mp.weighted_cm_ratio)})</span></span>` +
      `<span><span class="k">BLENDED BE</span><span class="v">${fmtNum(mp.blended_break_even_units)}u</span></span>` +
      `<span><span class="k">BLENDED BE REV</span><span class="v">${fmtCcy(mp.blended_break_even_revenue, ccy)}</span></span>`;
    let html = `<thead><tr>
      <th>Product</th><th>Mix %</th><th>Price</th><th>VC</th>
      <th>CM / unit</th><th>CM ratio</th><th>BE units (allocated)</th><th>BE revenue (allocated)</th>
    </tr></thead><tbody>`;
    mp.per_product.forEach(p => {
      html += `<tr>
        <td>${p.name}</td>
        <td>${fmtPct(p.mix_pct, 1)}</td>
        <td>${fmtCcy(p.price, ccy, 2)}</td>
        <td>${fmtCcy(p.vc, ccy, 2)}</td>
        <td>${fmtCcy(p.cm_per_unit, ccy, 2)}</td>
        <td>${fmtPct(p.cm_ratio)}</td>
        <td>${p.allocated_units === null ? "n/a" : fmtNum(p.allocated_units)}</td>
        <td>${p.allocated_revenue === null ? "n/a" : fmtCcy(p.allocated_revenue, ccy)}</td>
      </tr>`;
    });
    html += "</tbody>";
    $("#multi-table").innerHTML = html;
  }

  // ---- Step-cost table ----
  function renderStep(rows, ccy) {
    let html = `<thead><tr>
      <th>Segment</th><th>Volume range</th><th>Fixed cost at segment</th>
      <th>BE units (in segment)</th><th>Reachable here?</th>
    </tr></thead><tbody>`;
    rows.forEach(r => {
      const cls = r.is_reachable_in_segment ? "reachable" : "";
      const range = r.units_upper === null
        ? `${fmtNum(r.units_lower)}+`
        : `${fmtNum(r.units_lower)} - ${fmtNum(r.units_upper)}`;
      html += `<tr class="${cls}">
        <td>${r.segment}</td>
        <td>${range}</td>
        <td>${fmtCcy(r.fixed_cost_at_segment, ccy)}</td>
        <td>${r.break_even_units === null ? "n/a" : fmtNum(r.break_even_units)}</td>
        <td>${r.is_reachable_in_segment ? "YES" : "NO"}</td>
      </tr>`;
    });
    html += "</tbody>";
    $("#step-table").innerHTML = html;
  }

  // ---- 2D heatmap ----
  function renderHeatmap(grid, ccy) {
    const flat = grid.be_grid.flat().filter(x => x !== null);
    const lo = Math.min.apply(null, flat);
    const hi = Math.max.apply(null, flat);
    const colour = (be) => {
      if (be === null || !isFinite(be)) return "#FCE7F3";
      if (hi === lo) return "#FBCFE8";
      const t = (be - lo) / (hi - lo); // 0 (low BE = good) -> 1 (high BE = bad)
      const stops = ["#ECFDF5", "#D1FAE5", "#FCE7F3", "#FBCFE8", "#F472B6", "#EC4899"];
      const i = Math.min(stops.length - 1, Math.floor(t * (stops.length - 1)));
      return stops[i];
    };
    const mid = Math.floor(grid.deltas.length / 2);
    let html = `<table><thead><tr><th></th>`;
    grid.deltas.forEach((d, j) => {
      html += `<th>vc ${(d * 100 >= 0 ? "+" : "") + (d * 100).toFixed(0)}%</th>`;
    });
    html += `</tr></thead><tbody>`;
    grid.deltas.forEach((d, i) => {
      html += `<tr><td class="heat-cell-axis">price ${(d * 100 >= 0 ? "+" : "") + (d * 100).toFixed(0)}%</td>`;
      grid.be_grid[i].forEach((be, j) => {
        const baseline = (i === mid && j === mid) ? "heat-baseline" : "";
        html += `<td class="${baseline}" style="background:${colour(be)}">${be === null ? "n/a" : fmtNum(be)}</td>`;
      });
      html += `</tr>`;
    });
    html += `</tbody></table>`;
    return html;
  }

  // ---- Show-the-working ----
  function renderWorking(inp, h, ccy, body) {
    const cm = inp.price_per_unit - inp.variable_cost_per_unit;
    const be = inp.fixed_cost / cm;
    const sym = ({GBP:"£", USD:"$", EUR:"€"})[ccy] || "";
    const bits = [];
    bits.push(`<div class="step-label">1. Contribution margin per unit</div>`);
    bits.push(`<span class="formula">CM = price - vc = ${sym}${inp.price_per_unit.toFixed(2)} - ${sym}${inp.variable_cost_per_unit.toFixed(2)} = ${sym}${cm.toFixed(2)}</span>`);
    bits.push(`<div class="step-label">2. CM ratio</div>`);
    bits.push(`<span class="formula">CM ratio = CM / price = ${sym}${cm.toFixed(2)} / ${sym}${inp.price_per_unit.toFixed(2)} = ${fmtPct(h.cm_ratio)}</span>`);
    bits.push(`<div class="step-label">3. Break-even units</div>`);
    bits.push(`<span class="formula">BE units = fixed / CM = ${sym}${fmtNum(inp.fixed_cost)} / ${sym}${cm.toFixed(2)} = ${fmtNum(be)}</span>`);
    bits.push(`<div class="step-label">4. Break-even revenue</div>`);
    bits.push(`<span class="formula">BE revenue = BE units x price = ${fmtNum(be)} x ${sym}${inp.price_per_unit.toFixed(2)} = ${sym}${fmtNum(be * inp.price_per_unit)}</span>`);
    if (h.target_profit_units !== null && h.target_profit_units !== undefined && inp.target_profit) {
      bits.push(`<div class="step-label">5. Target-profit volume</div>`);
      bits.push(`<span class="formula">Units = (fixed + target) / CM = (${sym}${fmtNum(inp.fixed_cost)} + ${sym}${fmtNum(inp.target_profit)}) / ${sym}${cm.toFixed(2)} = ${fmtNum(h.target_profit_units)}</span>`);
    }
    if (h.margin_of_safety_units !== null && h.margin_of_safety_units !== undefined) {
      bits.push(`<div class="step-label">6. Margin of safety</div>`);
      bits.push(`<span class="formula">MoS units = current volume - BE = ${fmtNum((body.metadata||{}).current_volume)} - ${fmtNum(be)} = ${fmtNum(h.margin_of_safety_units)}</span>`);
    }
    if (h.cash_break_even_units !== null && h.cash_break_even_units !== undefined) {
      bits.push(`<div class="step-label">7. Cash break-even (excludes non-cash fixed)</div>`);
      bits.push(`<span class="formula">Cash BE = (fixed - non-cash) / CM = (${sym}${fmtNum(inp.fixed_cost)} - ${sym}${fmtNum((body.metadata||{}).non_cash_amount)}) / ${sym}${cm.toFixed(2)} = ${fmtNum(h.cash_break_even_units)}</span>`);
    }
    if (h.operating_leverage_at_current !== null && h.operating_leverage_at_current !== undefined) {
      bits.push(`<div class="step-label">8. Operating leverage</div>`);
      bits.push(`<span class="formula">Op leverage = contribution / profit = ${fmtNum(((body.metadata||{}).current_volume || 0) * cm)} / ${fmtNum(((body.metadata||{}).current_volume || 0) * cm - inp.fixed_cost)} = ${h.operating_leverage_at_current.toFixed(2)}x</span>`);
    }
    return bits.join("");
  }

  // ---- What-if sliders ----
  let _wfBase = null;
  function setupSliders(inp, md) {
    _wfBase = { inp: { ...inp }, md: { ...md } };
    const calibrate = (id, baseVal, min = 0.5, max = 1.5) => {
      const el = $(id);
      el.min = baseVal * min;
      el.max = baseVal * max;
      el.step = baseVal / 200 || 0.01;
      el.value = baseVal;
    };
    calibrate("#sl-price", inp.price_per_unit);
    calibrate("#sl-vc",    inp.variable_cost_per_unit, 0, 1.5);
    calibrate("#sl-fixed", inp.fixed_cost);
    if (md.current_volume) {
      calibrate("#sl-vol", md.current_volume);
    } else {
      calibrate("#sl-vol", Math.max(inp.fixed_cost / Math.max(inp.price_per_unit - inp.variable_cost_per_unit, 0.01), 100));
    }
    ["#sl-price","#sl-vc","#sl-fixed","#sl-vol"].forEach(s => {
      const el = $(s);
      el.oninput = recomputeWhatIf;
    });
    $("#whatif-reset").onclick = () => {
      calibrate("#sl-price", inp.price_per_unit);
      calibrate("#sl-vc",    inp.variable_cost_per_unit, 0, 1.5);
      calibrate("#sl-fixed", inp.fixed_cost);
      calibrate("#sl-vol",   md.current_volume || (inp.fixed_cost / Math.max(inp.price_per_unit - inp.variable_cost_per_unit, 0.01)));
      recomputeWhatIf();
    };
    recomputeWhatIf();
  }
  function recomputeWhatIf() {
    const ccy = (_wfBase && _wfBase.md.currency) || "GBP";
    const price = parseFloat($("#sl-price").value);
    const vc    = parseFloat($("#sl-vc").value);
    const fixed = parseFloat($("#sl-fixed").value);
    const vol   = parseFloat($("#sl-vol").value);
    $("#sl-price-v").textContent = fmtCcy(price, ccy, 2);
    $("#sl-vc-v").textContent    = fmtCcy(vc, ccy, 2);
    $("#sl-fixed-v").textContent = fmtCcy(fixed, ccy);
    $("#sl-vol-v").textContent   = fmtNum(vol) + "u";
    const cm = price - vc;
    const cmRatio = price > 0 ? cm / price : 0;
    const be = cm > 0 ? fixed / cm : null;
    const mos = (be !== null && vol > 0) ? vol - be : null;
    const profit = cm * vol - fixed;

    const baseInp = _wfBase.inp, baseMd = _wfBase.md;
    const baseCm = baseInp.price_per_unit - baseInp.variable_cost_per_unit;
    const baseBe = baseCm > 0 ? baseInp.fixed_cost / baseCm : null;
    const baseProfit = baseCm * (baseMd.current_volume || 0) - baseInp.fixed_cost;

    setWf("#wf-be", be === null ? "NEVER" : fmtNum(be) + "u",
          deltaTag(be, baseBe, "u"));
    setWf("#wf-cm", fmtPct(cmRatio),
          deltaTag(cmRatio, baseCm > 0 ? baseCm / baseInp.price_per_unit : null, "%"));
    setWf("#wf-mos", mos === null ? "n/a" : fmtNum(mos) + "u",
          baseBe === null ? "" : deltaTag(mos, (baseMd.current_volume || 0) - baseBe, "u"));
    setWf("#wf-profit", fmtCcy(profit, ccy),
          deltaTag(profit, baseProfit, ccy));
  }
  function setWf(id, value, deltaObj) {
    $(id).textContent = value;
    const dEl = $(id + "-d");
    dEl.textContent = deltaObj.text;
    dEl.classList.toggle("is-up", deltaObj.kind === "up");
    dEl.classList.toggle("is-down", deltaObj.kind === "down");
  }
  function deltaTag(now, base, suffix) {
    if (now === null || base === null || !isFinite(now) || !isFinite(base) || base === 0) {
      return { text: "vs base: n/a", kind: "" };
    }
    const d = now - base;
    if (Math.abs(d) < 0.0001) return { text: "vs base: -", kind: "" };
    const sign = d > 0 ? "+" : "";
    let text;
    if (suffix === "%")     text = "vs base: " + sign + (d * 100).toFixed(2) + "%";
    else if (suffix === "u") text = "vs base: " + sign + fmtNum(d) + "u";
    else                     text = "vs base: " + sign + fmtCcy(d, suffix);
    const kind = d > 0 ? "up" : "down";
    return { text, kind };
  }

  // ---- Targets calculator ----
  function setupTargets(inp, md, ccy) {
    const cm = inp.price_per_unit - inp.variable_cost_per_unit;
    const update = () => {
      const v = parseFloat($("#t-vol").value);
      $("#t-vol-out").textContent = isFinite(v)
        ? `profit: ${fmtCcy(cm * v - inp.fixed_cost, ccy)}` : "profit: --";
      const p = parseFloat($("#t-prof").value);
      $("#t-prof-out").textContent = isFinite(p)
        ? `units: ${cm > 0 ? fmtNum((inp.fixed_cost + p) / cm) : "n/a"}` : "units: --";
      const m = parseFloat($("#t-margin").value);
      $("#t-margin-out").textContent = isFinite(m) && m < 1 && m > 0
        ? `price: ${fmtCcy(inp.variable_cost_per_unit / (1 - m), ccy, 2)}` : "price: --";
    };
    $("#t-vol").value = (md.current_volume || "");
    $("#t-prof").value = (inp.target_profit || "");
    $("#t-margin").value = "";
    ["#t-vol","#t-prof","#t-margin"].forEach(s => $(s).oninput = update);
    update();
  }

  // ---- Compare three prices ----
  function setupCompare3(inp, md, ccy) {
    const inputs = $$(".comp3-input");
    const defaults = [
      inp.price_per_unit * 0.95,
      inp.price_per_unit,
      inp.price_per_unit * 1.05,
    ];
    inputs.forEach((el, i) => {
      el.value = defaults[i].toFixed(2);
      el.oninput = recomputeC3;
    });
    function recomputeC3() {
      $$(".comp3-cell").forEach(cell => {
        const price = parseFloat(cell.querySelector('input[data-role="price"]').value);
        if (!isFinite(price) || price <= inp.variable_cost_per_unit) {
          cell.querySelector('[data-out="be"]').textContent  = "n/a";
          cell.querySelector('[data-out="cm"]').textContent  = "n/a";
          cell.querySelector('[data-out="mos"]').textContent = "n/a";
          return;
        }
        const cm = price - inp.variable_cost_per_unit;
        const be = inp.fixed_cost / cm;
        const cmRatio = cm / price;
        const mos = md.current_volume ? (md.current_volume - be) : null;
        cell.querySelector('[data-out="be"]').textContent  = fmtNum(be) + "u";
        cell.querySelector('[data-out="cm"]').textContent  = fmtPct(cmRatio);
        cell.querySelector('[data-out="mos"]').textContent = mos === null ? "n/a" : fmtNum(mos) + "u";
      });
    }
    recomputeC3();
  }

  // ---- AI follow-up ----
  $("#followup-btn").onclick = async () => {
    const q = $("#followup-input").value.trim();
    if (!q) return;
    if (!lastBody || !lastBody.run_id) {
      $("#followup-status").textContent = "Run an analysis first.";
      return;
    }
    $("#followup-status").textContent = "Asking the CFO...";
    $("#followup-answer").hidden = true;
    const fd = new FormData();
    fd.append("run_id", lastBody.run_id);
    fd.append("question", q);
    try {
      const res = await fetch("/api/followup", {
        method: "POST", body: fd, headers: csrfHeaders(),
      });
      const j = await res.json();
      if (j.error) {
        $("#followup-status").textContent = "Error: " + j.error;
        return;
      }
      $("#followup-answer").textContent = j.answer || "(empty answer)";
      $("#followup-answer").hidden = false;
      $("#followup-status").textContent =
        `cost $${(j.cost_usd || 0).toFixed(5)} / model ${j.model || ""}`;
    } catch (e) {
      $("#followup-status").textContent = "Failed: " + (e.message || String(e));
    }
  };
  $("#followup-input").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); $("#followup-btn").click(); }
  });

  // ---- Save / load named runs ----
  function loadSaved() {
    try { return JSON.parse(localStorage.getItem("day06.savedRuns.v1") || "[]"); }
    catch (_) { return []; }
  }
  function persistSaved() {
    try { localStorage.setItem("day06.savedRuns.v1", JSON.stringify(savedRuns.slice(-30))); }
    catch (_) {}
  }
  $("#save-run-btn").onclick = async () => {
    if (!lastBody || !lastBody.run_id) return;
    const label = (prompt("Label this scenario:", lastBody.metadata.company || "scenario") || "").trim();
    if (!label) return;
    const fd = new FormData();
    fd.append("label", label);
    try {
      const res = await fetch(`/api/runs/${lastBody.run_id}/save`, {
        method: "POST", body: fd, headers: csrfHeaders(),
      });
      const j = await res.json();
      if (!res.ok) { setStatus("Save failed: " + (j.error || res.status), "error"); return; }
    } catch (_) {}
    savedRuns = savedRuns.filter(r => r.run_id !== lastBody.run_id);
    savedRuns.push({
      run_id: lastBody.run_id, label,
      company: lastBody.metadata.company,
      currency: lastBody.metadata.currency,
      be: (lastBody.headline || {}).break_even_units,
      ts: Date.now(),
    });
    persistSaved();
    refreshSavedList();
    setStatus(`SAVED AS "${label.toUpperCase()}"`, "ok");
  };
  function refreshSavedList() {
    if (!savedRuns.length) { hide(savedBlock); return; }
    show(savedBlock);
    savedList.innerHTML = "";
    savedRuns.slice().reverse().forEach(s => {
      const li = document.createElement("li");
      li.innerHTML = `
        <input type="checkbox" data-rid="${s.run_id}">
        <span class="saved-label" data-rid="${s.run_id}">${escapeHtml(s.label)} - ${escapeHtml(s.company || "")}</span>
      `;
      li.querySelector(".saved-label").onclick = () => loadCachedRun(s.run_id);
      savedList.appendChild(li);
    });
    $("#compare-pick").hidden = savedRuns.length < 2;
  }
  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, ch =>
      ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[ch]);
  }
  async function loadCachedRun(runId) {
    setStatus("Loading saved run...");
    try {
      const res = await fetch(`/api/runs/${runId}`);
      const j = await res.json();
      if (!res.ok) { setStatus("Load failed: " + (j.error || res.status), "error"); return; }
      lastBody = j;
      render(j);
      setStatus("LOADED", "ok");
    } catch (e) {
      setStatus("Load failed: " + e.message, "error");
    }
  }
  $("#compare-btn").onclick = async () => {
    const checked = $$(".saved-list input[type='checkbox']:checked")
      .map(c => c.getAttribute("data-rid"));
    if (checked.length !== 2) {
      setStatus("Pick exactly two runs to compare.", "error");
      return;
    }
    const fd = new FormData();
    fd.append("a", checked[0]);
    fd.append("b", checked[1]);
    const res = await fetch("/api/compare", {
      method: "POST", body: fd, headers: csrfHeaders(),
    });
    const j = await res.json();
    if (!res.ok) { setStatus("Compare failed: " + (j.error || res.status), "error"); return; }
    renderCompare(j);
    show(compareCard);
    compareCard.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  function renderCompare(j) {
    const ccy = (lastBody && lastBody.metadata && lastBody.metadata.currency) || "GBP";
    let html = `<thead><tr>
      <th>Metric</th>
      <th>${escapeHtml(j.a_company || j.a_id)} (A)</th>
      <th>${escapeHtml(j.b_company || j.b_id)} (B)</th>
      <th>Delta (B - A)</th>
      <th>Delta %</th>
    </tr></thead><tbody>`;
    const order = [
      ["break_even_units", "BE units", "units"],
      ["break_even_revenue", "BE revenue", "ccy"],
      ["cm_ratio", "CM ratio", "pct"],
      ["contribution_margin_per_unit", "CM per unit", "ccy"],
      ["margin_of_safety_units", "MoS units", "units"],
      ["margin_of_safety_pct", "MoS %", "pct"],
      ["target_profit_units", "Target profit units", "units"],
      ["operating_leverage_at_current", "Op leverage", "x"],
      ["cash_break_even_units", "Cash BE", "units"],
    ];
    const f = (v, kind) => {
      if (v === null || v === undefined) return "n/a";
      if (kind === "ccy") return fmtCcy(v, ccy);
      if (kind === "pct") return fmtPct(v);
      if (kind === "x") return v.toFixed(2) + "x";
      return fmtNum(v);
    };
    order.forEach(([k, label, kind]) => {
      const d = j.deltas[k] || {};
      const cls = d.delta === null ? "" : (d.delta > 0 ? "delta-pos" : (d.delta < 0 ? "delta-neg" : ""));
      html += `<tr>
        <td>${label}</td>
        <td>${f(d.a, kind)}</td>
        <td>${f(d.b, kind)}</td>
        <td class="${cls}">${d.delta === null ? "n/a" : (d.delta > 0 ? "+" : "") + f(d.delta, kind)}</td>
        <td class="${cls}">${d.delta_pct === null ? "n/a" : (d.delta_pct > 0 ? "+" : "") + fmtPct(d.delta_pct)}</td>
      </tr>`;
    });
    html += "</tbody>";
    $("#compare-table").innerHTML = html;
  }

  // ---- Mix-shift sliders for multi-product ----
  let _mixState = null;
  function setupMixSliders(mp, inp, ccy) {
    const host = $("#mix-sliders");
    host.innerHTML = "";
    _mixState = mp.per_product.map(p => ({ name: p.name, price: p.price, vc: p.vc, mix: p.mix_pct }));
    _mixState.forEach((p, i) => {
      const row = document.createElement("div");
      row.className = "mix-row";
      row.innerHTML = `
        <span class="mix-name">${escapeHtml(p.name)}</span>
        <input type="range" data-i="${i}" min="0" max="1" step="0.01" value="${p.mix.toFixed(2)}">
        <span class="mix-pct" data-pct="${i}">${(p.mix * 100).toFixed(0)}%</span>
      `;
      host.appendChild(row);
    });
    const warn = document.createElement("div");
    warn.className = "mix-warn";
    warn.id = "mix-warn";
    host.appendChild(warn);
    host.querySelectorAll('input[type="range"]').forEach(el => {
      el.oninput = () => {
        const i = parseInt(el.getAttribute("data-i"), 10);
        _mixState[i].mix = parseFloat(el.value);
        recomputeMix(inp, ccy);
      };
    });
    $("#mix-reset").onclick = () => {
      mp.per_product.forEach((p, i) => {
        _mixState[i].mix = p.mix_pct;
        host.querySelector(`input[data-i="${i}"]`).value = p.mix_pct;
      });
      recomputeMix(inp, ccy);
    };
    recomputeMix(inp, ccy);
  }
  function recomputeMix(inp, ccy) {
    const total = _mixState.reduce((a, b) => a + b.mix, 0);
    const warn = $("#mix-warn");
    warn.textContent = total > 0 && Math.abs(total - 1) > 0.01
      ? `mix sums to ${(total * 100).toFixed(0)}% - auto-normalised below`
      : "";
    let weightedPrice = 0, weightedVc = 0;
    _mixState.forEach((p, i) => {
      const norm = total > 0 ? p.mix / total : 0;
      weightedPrice += p.price * norm;
      weightedVc += p.vc * norm;
      const el = $("#mix-sliders").querySelector(`[data-pct="${i}"]`);
      if (el) el.textContent = (norm * 100).toFixed(0) + "%";
    });
    const cm = weightedPrice - weightedVc;
    const cmRatio = weightedPrice > 0 ? cm / weightedPrice : 0;
    const be = cm > 0 ? inp.fixed_cost / cm : null;
    const beRev = be !== null ? be * weightedPrice : null;
    const sum = $("#multi-summary");
    sum.innerHTML =
      `<span><span class="k">WEIGHTED PRICE</span><span class="v">${fmtCcy(weightedPrice, ccy, 2)}</span></span>` +
      `<span><span class="k">WEIGHTED VC</span><span class="v">${fmtCcy(weightedVc, ccy, 2)}</span></span>` +
      `<span><span class="k">WEIGHTED CM</span><span class="v">${fmtCcy(cm, ccy, 2)} (${fmtPct(cmRatio)})</span></span>` +
      `<span><span class="k">BLENDED BE</span><span class="v">${be === null ? "n/a" : fmtNum(be) + "u"}</span></span>` +
      `<span><span class="k">BLENDED BE REV</span><span class="v">${beRev === null ? "n/a" : fmtCcy(beRev, ccy)}</span></span>`;
  }

  // ---- Monte Carlo histogram + summary ----
  function renderMonteCarlo(mc) {
    $("#mc-summary").innerHTML =
      `<div class="mc-stat is-band">
         <div class="k">P5</div><div class="v">${fmtNum(mc.p5_be)}u</div>
       </div>
       <div class="mc-stat">
         <div class="k">P25</div><div class="v">${fmtNum(mc.p25_be)}u</div>
       </div>
       <div class="mc-stat">
         <div class="k">MEDIAN</div><div class="v">${fmtNum(mc.median_be)}u</div>
       </div>
       <div class="mc-stat">
         <div class="k">P75</div><div class="v">${fmtNum(mc.p75_be)}u</div>
       </div>
       <div class="mc-stat is-band">
         <div class="k">P95</div><div class="v">${fmtNum(mc.p95_be)}u</div>
       </div>`;
    $("#mc-host").innerHTML = renderHistogramSVG(mc);
  }
  function renderHistogramSVG(mc) {
    const w = 920, h = 200, pad = 30;
    if (!mc.histogram || !mc.histogram.length) return "";
    const innerW = w - 2 * pad, innerH = h - 2 * pad;
    const maxCount = Math.max.apply(null, mc.histogram.map(b => b.count));
    if (maxCount === 0) return "";
    const lo = mc.histogram[0].bin_lo;
    const hi = mc.histogram[mc.histogram.length - 1].bin_hi;
    const xRange = hi - lo;
    const barW = innerW / mc.histogram.length;
    const xAt = v => pad + ((v - lo) / xRange) * innerW;
    const ink = "#0F1117", magenta = "#EC4899", grey = "#6B7280", purple = "#7C3AED";
    const parts = [];
    parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="100%" height="${h}">`);
    parts.push(`<rect x="${pad}" y="${pad}" width="${innerW}" height="${innerH}" fill="none" stroke="${ink}" stroke-width="1.0"/>`);
    mc.histogram.forEach((b, i) => {
      const bh = (b.count / maxCount) * innerH;
      const x = pad + i * barW;
      const y = pad + (innerH - bh);
      parts.push(`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(barW - 1).toFixed(1)}" height="${bh.toFixed(1)}" fill="${magenta}" opacity="${0.30 + 0.55 * (b.count / maxCount)}"/>`);
    });
    // Percentile lines
    const lines = [
      { v: mc.p5_be,     stroke: purple, dash: "4 4", label: "P5" },
      { v: mc.median_be, stroke: ink,    dash: "",    label: "MED" },
      { v: mc.p95_be,    stroke: purple, dash: "4 4", label: "P95" },
    ];
    lines.forEach(l => {
      const x = xAt(l.v);
      parts.push(`<line x1="${x.toFixed(1)}" y1="${pad}" x2="${x.toFixed(1)}" y2="${pad + innerH}" stroke="${l.stroke}" stroke-width="1.4" stroke-dasharray="${l.dash}"/>`);
      parts.push(`<text x="${x.toFixed(1)}" y="${(pad - 6).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9.5" font-weight="700" fill="${l.stroke}" text-anchor="middle">${l.label} ${Math.round(l.v).toLocaleString()}</text>`);
    });
    parts.push(`<text x="${pad.toFixed(1)}" y="${(h - 8).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9" fill="${grey}">${Math.round(lo).toLocaleString()}u</text>`);
    parts.push(`<text x="${(pad + innerW).toFixed(1)}" y="${(h - 8).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9" fill="${grey}" text-anchor="end">${Math.round(hi).toLocaleString()}u</text>`);
    parts.push(`<text x="${(w / 2).toFixed(1)}" y="${(h - 8).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9" fill="${grey}" text-anchor="middle">BE units distribution (${mc.n_runs.toLocaleString()} runs, +/-${(mc.span_pct * 100).toFixed(0)}%${mc.pct_undefined > 0 ? `, ${(mc.pct_undefined * 100).toFixed(1)}% undefined` : ""})</text>`);
    parts.push(`</svg>`);
    return parts.join("");
  }

  $("#mc-rerun").addEventListener("click", async () => {
    if (!lastBody) return;
    const fd = new FormData();
    fd.append("price_per_unit", lastBody.inputs.price_per_unit);
    fd.append("variable_cost_per_unit", lastBody.inputs.variable_cost_per_unit);
    fd.append("fixed_cost", lastBody.inputs.fixed_cost);
    fd.append("n_runs", $("#mc-runs").value);
    fd.append("span_pct", $("#mc-span").value);
    fd.append("seed", "42");
    const res = await fetch("/api/montecarlo", {
      method: "POST", body: fd, headers: csrfHeaders(),
    });
    const j = await res.json();
    if (!res.ok) {
      setStatus("MC failed: " + (j.error || res.status), "error");
      return;
    }
    renderMonteCarlo(j);
  });

  // ---- Time-phased BE ----
  function renderTimePhased(rows, firstCrossing, ccy) {
    const summary = firstCrossing
      ? `Cumulative break-even crosses in <span class="ok">${firstCrossing}</span>.`
      : `Cumulative break-even is <span class="warn">not reached</span> within the planned horizon.`;
    $("#time-summary").innerHTML = summary;

    // Mini SVG chart of cumulative profit
    const w = 920, h = 180, pad = 32;
    const innerW = w - 2 * pad, innerH = h - 2 * pad;
    const ys = rows.map(r => r.cumulative_profit);
    const yMin = Math.min(0, Math.min.apply(null, ys));
    const yMax = Math.max(0, Math.max.apply(null, ys));
    const yAt = v => pad + (1 - (v - yMin) / (yMax - yMin || 1)) * innerH;
    const xAt = i => pad + (i / Math.max(1, rows.length - 1)) * innerW;
    const ink = "#0F1117", magenta = "#EC4899", purple = "#7C3AED", grey = "#6B7280", green = "#10B981";
    const parts = [];
    parts.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="100%" height="${h}">`);
    parts.push(`<rect x="${pad}" y="${pad}" width="${innerW}" height="${innerH}" fill="none" stroke="${ink}" stroke-width="1"/>`);
    // Zero line
    if (yMin < 0 && yMax > 0) {
      const y0 = yAt(0);
      parts.push(`<line x1="${pad}" y1="${y0.toFixed(1)}" x2="${(pad + innerW).toFixed(1)}" y2="${y0.toFixed(1)}" stroke="${grey}" stroke-width="0.8" stroke-dasharray="2 4"/>`);
      parts.push(`<text x="${(pad + 4).toFixed(1)}" y="${(y0 - 4).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9" fill="${grey}">cumulative break-even = 0</text>`);
    }
    // Polyline of cumulative profit
    const pts = rows.map((r, i) => `${xAt(i).toFixed(1)},${yAt(r.cumulative_profit).toFixed(1)}`).join(" ");
    parts.push(`<polyline points="${pts}" fill="none" stroke="${purple}" stroke-width="2.4"/>`);
    // Markers
    rows.forEach((r, i) => {
      const x = xAt(i), y = yAt(r.cumulative_profit);
      const fill = r.crossed ? magenta : (r.cumulative_profit >= 0 ? green : ink);
      const sz = r.crossed ? 7 : 4;
      parts.push(`<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${sz}" fill="${fill}" stroke="${ink}" stroke-width="${r.crossed ? 1.5 : 0.6}"/>`);
      parts.push(`<text x="${x.toFixed(1)}" y="${(pad + innerH + 14).toFixed(1)}" font-family="JetBrains Mono, ui-monospace, monospace" font-size="9" fill="${grey}" text-anchor="middle">${escapeHtml(r.period_label)}</text>`);
    });
    parts.push(`</svg>`);
    $("#time-host").innerHTML = parts.join("");

    let html = `<thead><tr>
      <th>Period</th><th>Units this period</th><th>Cumulative units</th>
      <th>Cumulative profit</th><th>BE crossed?</th>
    </tr></thead><tbody>`;
    rows.forEach(r => {
      const cls = r.crossed ? "is-cross" : "";
      const profitCls = r.cumulative_profit >= 0 ? "profit-pos" : "profit-neg";
      html += `<tr class="${cls}">
        <td>${escapeHtml(r.period_label)}</td>
        <td>${fmtNum(r.units)}</td>
        <td>${fmtNum(r.cumulative_units)}</td>
        <td class="${profitCls}">${fmtCcy(r.cumulative_profit, ccy)}</td>
        <td>${r.crossed ? "YES" : (r.cumulative_profit >= 0 ? "(already)" : "no")}</td>
      </tr>`;
    });
    html += "</tbody>";
    $("#time-table").innerHTML = html;
  }

  // ---- URL state encoding (shareable scenarios) ----
  function syncURL(inp, md) {
    const params = new URLSearchParams();
    params.set("p", inp.price_per_unit);
    params.set("v", inp.variable_cost_per_unit);
    params.set("f", inp.fixed_cost);
    if (md.current_volume) params.set("q", md.current_volume);
    if (inp.target_profit) params.set("t", inp.target_profit);
    if (md.currency) params.set("c", md.currency);
    history.replaceState(null, "", "?" + params.toString());
  }
  $("#share-btn").onclick = async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      setStatus("URL COPIED TO CLIPBOARD", "ok");
    } catch (_) {
      setStatus(location.href, "ok");
    }
  };

  // ---- Print ----
  $("#print-btn").onclick = () => window.print();

  // ---- Restore last result on load ----
  try {
    const cached = localStorage.getItem("day06.lastResult.v1");
    if (cached) {
      const body = JSON.parse(cached);
      lastBody = body;
      render(body);
      setStatus("RESTORED FROM LOCAL CACHE", "ok");
    }
  } catch (_) {}

  refreshSavedList();
})();
