/* Renders research.html from RESEARCH (research_data.js). Supports multiple frozen experiments. Historical backtests only. */
function rPct(v, d = 1) {
  if (v == null || !Number.isFinite(v)) return "—";
  const s = v > 0 ? "+" : v < 0 ? "−" : "";
  return s + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) + "%";
}
function rNum(v, d = 2) { return v == null || !Number.isFinite(v) ? "—" : (v < 0 ? "−" : "") + Math.abs(v).toFixed(d); }
function esc(t) { return String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
const VERDICT_TONE = { Promising: "up", Mixed: "flat", Failed: "down" };

function logChart(s) {
  const W = 720, H = 300, pad = { l: 96, r: 18, t: 18, b: 34 };
  const all = s.curve.concat(s.holdCurve).map((p) => p[1]).filter((v) => v > 0);
  const lo = Math.log10(Math.min(...all, 10000) * 0.9), hi = Math.log10(Math.max(...all) * 1.1);
  const t0 = Date.parse(s.curve[0][0]), t1 = Date.parse(s.curve[s.curve.length - 1][0]);
  const x = (d) => pad.l + ((Date.parse(d) - t0) / (t1 - t0)) * (W - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (Math.log10(v) - lo) / (hi - lo)) * (H - pad.t - pad.b);
  let g = "";
  const ticks = [];
  for (let e = Math.floor(lo); e <= Math.ceil(hi); e++) [1, 3].forEach((m) => { const v = m * 10 ** e; if (Math.log10(v) >= lo && Math.log10(v) <= hi) ticks.push(v); });
  ticks.forEach((v) => {
    g += `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}" stroke="${v === 10000 ? "#5c4634" : "#241e19"}" stroke-width="${v === 10000 ? 1.5 : 1}"/>`;
    g += `<text x="6" y="${y(v) + 5}" font-size="15">$${v >= 1e6 ? (v / 1e6) + "M" : v >= 1e3 ? (v / 1e3) + "k" : v}</text>`;
  });
  const y0 = new Date(t0).getUTCFullYear(), y1 = new Date(t1).getUTCFullYear(), step = y1 - y0 > 14 ? 5 : 2;
  for (let yr = Math.ceil(y0 / step) * step; yr <= y1; yr += step) {
    const xx = x(yr + "-01-01"); if (xx < pad.l || xx > W - pad.r) continue;
    g += `<text x="${xx}" y="${H - 10}" font-size="15" text-anchor="middle">${yr}</text>`;
  }
  const line = (pts, color, dash) => `<polyline fill="none" stroke="${color}" stroke-width="3" ${dash ? `stroke-dasharray="${dash}"` : ""} points="${pts.map((p) => x(p[0]) + "," + y(p[1])).join(" ")}"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(s.name)} growth of $10,000 versus buy-and-hold, log scale">${g}${line(s.holdCurve, "#8a7a66", "3 6")}${line(s.curve, s.color, "")}</svg>`;
}

function table(s) {
  const f = s.full, r = s.recent;
  const row = (label, fn) => `<tr><th>${label}</th><td>${fn(f.strat)}</td><td>${fn(f.hold)}</td><td>${fn(r.strat)}</td><td>${fn(r.hold)}</td></tr>`;
  return `<div class="rtable"><table>
    <thead><tr><th></th><th colspan="2">Long window ${f.from.slice(0, 4)}–${f.to.slice(0, 4)}</th><th colspan="2">Recent ${r.from.slice(0, 7)} → ${r.to.slice(0, 7)}</th></tr>
    <tr><th></th><th>Strategy</th><th>Buy &amp; hold</th><th>Strategy</th><th>Buy &amp; hold</th></tr></thead>
    <tbody>
    ${row("Total return", (m) => rPct(m.total_return_pct))}
    ${row("CAGR", (m) => rPct(m.cagr_pct))}
    ${row("Max drawdown", (m) => rPct(m.max_dd_pct))}
    ${row("Sharpe", (m) => rNum(m.sharpe))}
    <tr><th>Trades (closed)</th><td>${f.strat.trades}${f.strat.open_trades ? " + 1 open" : ""}</td><td>1</td><td>${r.strat.trades}${r.strat.open_trades ? " + 1 open" : ""}</td><td>1</td></tr>
    <tr><th>Win rate</th><td>${f.strat.win_rate_pct == null ? "—" : f.strat.win_rate_pct + "%"}</td><td>—</td><td>${r.strat.win_rate_pct == null ? "—" : r.strat.win_rate_pct + "%"}</td><td>—</td></tr>
    <tr><th>Time in market</th><td>${f.strat.exposure_pct}%</td><td>100%</td><td>${r.strat.exposure_pct}%</td><td>100%</td></tr>
    </tbody></table></div>
    <p class="meta">Sensitivity, long window: filled at the signal close ${rPct(f.closeFill.total_return_pct)}; doubled fees ${rPct(f.doubleFeeReturn)}. Fees ${s.feePct.toFixed(2)}% per side. $10,000 start.</p>`;
}

function experimentList(R) {
  if (Array.isArray(R.experiments) && R.experiments.length) return R.experiments;
  return [{
    id: "legacy",
    date: "",
    label: R.label || "Historical backtests",
    folder: "",
    method: R.method || [],
    dataManifest: R.dataManifest || {},
    strategies: R.strategies || [],
  }];
}

function renderExperiment(exp, host) {
  const section = document.createElement("section");
  section.className = "research-run";
  section.id = exp.id;
  const dateLabel = exp.date ? `Run date ${esc(exp.date)}` : "Frozen run";
  const counts = { Promising: 0, Mixed: 0, Failed: 0 }; let pass = 0;
  exp.strategies.forEach((s) => { counts[s.verdict]++; if (s.ddLimit === "PASS") pass++; });
  const folder = exp.folder || "";
  const man = exp.dataManifest || {};
  const retrieved = (man.retrieved_et || man.retrieved_utc || "").toString().trim();

  section.innerHTML = `
    <header class="run-head">
      <p class="eyebrow">${esc(exp.label)}</p>
      <h2>${dateLabel}</h2>
      <p class="meta">Frozen folder <code>${esc(folder || exp.id)}</code>. Results files in that run were not recalculated for this page.</p>
    </header>
    <div class="tally">${[["up", counts.Promising, "Promising"], ["flat", counts.Mixed, "Mixed"], ["down", counts.Failed, "Failed"], [pass ? "up" : "down", pass + " of " + exp.strategies.length, "Pass 10% drawdown limit"]]
      .map(([t, c, l]) => `<article class="tone-${t}"><strong>${c}</strong><span>${l}</span></article>`).join("")}</div>
    <section class="ladder" data-fold-title="Ranked results · ${esc(exp.date || exp.id)}" data-fold-sum="History, not live signals." data-fold-group="research" data-fold-id="${esc(exp.id)}-table">
      <h2>Ranked by the pre-written verdict rule, then Sharpe versus buy-and-hold</h2>
      <div class="rtable"><table>
        <thead><tr><th>Strategy</th><th>Market</th><th>Return</th><th>Max DD</th><th>Hold return</th><th>Hold DD</th><th>Recent</th><th>Hold recent</th><th>Verdict</th><th>10% limit</th></tr></thead>
        <tbody>
        ${exp.strategies.map((s) => `<tr><th><a href="#${esc(exp.id)}-${esc(s.key)}">${esc(s.name)}</a></th><td>${esc(s.market)}</td><td>${rPct(s.full.strat.total_return_pct, 0)}</td><td>${rPct(s.full.strat.max_dd_pct)}</td><td>${rPct(s.full.hold.total_return_pct, 0)}</td><td>${rPct(s.full.hold.max_dd_pct)}</td><td>${rPct(s.recent.strat.total_return_pct)}</td><td>${rPct(s.recent.hold.total_return_pct)}</td><td class="tone-${VERDICT_TONE[s.verdict]}">${s.verdict}</td><td class="${s.ddLimit === "PASS" ? "tone-up" : "tone-down"}">${s.ddLimit}</td></tr>`).join("")}
        </tbody>
      </table></div>
    </section>
    <section class="ladder" data-fold-title="How this run was tested · ${esc(exp.date || exp.id)}" data-fold-sum="Fees, windows, and the frozen run." data-fold-group="research" data-fold-id="${esc(exp.id)}-method">
      <h2>How this run was tested</h2>
      <ul class="rules">${(exp.method || []).map((m) => `<li>${esc(m)}</li>`).join("")}</ul>
      <p class="meta">Data snapshot retrieved ${esc(retrieved)} ET. Code and results: <a href="${esc(folder)}/backtest.py">backtest.py</a> · <a href="${esc(folder)}/results.json">results.json</a> · <a href="${esc(folder)}/manifest.json">data hashes</a>.</p>
    </section>
    <div class="rgrid" data-fold-title="Strategies · ${esc(exp.date || exp.id)}" data-fold-sum="Open a row for the chart and the rules." data-fold-group="research" data-fold-id="${esc(exp.id)}-cards"></div>
  `;
  host.append(section);
  const cards = section.querySelector(".rgrid");
  exp.strategies.forEach((s, i) => {
    const tone = VERDICT_TONE[s.verdict];
    const el = document.createElement("article");
    el.className = "rcard card tone-" + tone + " drawer";
    el.id = `${exp.id}-${s.key}`;
    el.setAttribute("data-drawer-group", "research");
    el.innerHTML = `
      <button type="button" class="row-toggle" aria-expanded="false"><span class="row-name">${esc(s.name)}</span><span class="row-pnl">${rPct(s.full.strat.total_return_pct, 0)} · ${esc(s.verdict)}</span><span class="fold-chevron" aria-hidden="true"></span></button>
      <div class="drawer-body">
      <div class="card-top"><span class="num">R${String(i + 1).padStart(2, "0")} · ${esc(s.category)}</span><span class="tag">${esc(exp.date || exp.id)} · ${esc(s.market)}</span></div>
      <h2>${esc(s.name)}</h2>
      <p class="plain">${esc(s.plain)}</p>
      <div class="result"><span class="figure">${rPct(s.full.strat.total_return_pct, 0)}</span><span class="status">${s.verdict} · drawdown limit ${s.ddLimit}</span></div>
      <div class="plot rplot">${logChart(s)}</div>
      <div class="legend"><span><i class="swatch" style="border-top-color:${s.color}"></i>Strategy, $10,000 start</span><span><i class="swatch dash" style="border-top-color:#8a7a66"></i>Buy-and-hold</span><span>Log scale · month-end marks · ${s.full.from} → ${s.full.to}</span></div>
      ${table(s)}
      <h3>Why we picked it</h3><p class="why">${esc(s.why)}</p>
      <h3>Rules used (frozen)</h3><ul class="rules">${s.rules.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      <p class="meta"><b>Interpretation:</b> ${esc(s.interpretation)}</p>
      <p class="meta"><b>Source:</b> ${s.sources.map((x) => `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.label)}</a>`).join(" · ")}</p>
      </div>`;
    cards.append(el);
  });
}

function renderResearch() {
  const R = RESEARCH;
  const experiments = experimentList(R);
  document.getElementById("rlabel").textContent = R.label;
  const dates = experiments.map((e) => e.date).filter(Boolean);
  const preview = document.getElementById("rpreview");
  if (preview) {
    preview.innerHTML = [
      "<span>Historical backtest</span>",
      ...dates.map((d) => `<span>Run ${esc(d)}</span>`),
      "<span>Not financial advice</span>",
    ].join("");
  }
  const nav = document.getElementById("rruns");
  if (nav) {
    nav.innerHTML = `<p class="meta">Experiments on this page:</p><ul class="rules">${experiments.map((e) =>
      `<li><a href="#${esc(e.id)}">${esc(e.label)}</a> — run date <b>${esc(e.date || "—")}</b>, folder <code>${esc(e.folder || e.id)}</code></li>`
    ).join("")}</ul>`;
  }
  const host = document.getElementById("rexperiments");
  host.innerHTML = "";
  experiments.forEach((exp) => renderExperiment(exp, host));
}
