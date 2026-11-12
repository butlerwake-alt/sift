function money(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function shortDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return names[month - 1] + " " + day;
}

function signedPct(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return sign + Math.abs(value).toFixed(2) + "%";
}

function signedMoney(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return sign + money(Math.abs(value));
}

function dayCount(start, end) {
  if (!start || !end) return null;
  return Math.round((Date.parse(end + "T00:00:00Z") - Date.parse(start + "T00:00:00Z")) / 86400000);
}

function versusText(gap) {
  if (gap == null || !Number.isFinite(gap)) return "No buy-and-hold benchmark recorded";
  if (Math.abs(gap) < 0.005) return "Even with buy-and-hold";
  return (gap > 0 ? "Ahead of buy-and-hold by " : "Behind buy-and-hold by ") + Math.abs(gap).toFixed(2) + " points";
}

function drawChart(host, strategy, options = {}) {
  const compact = !!options.compact;
  const width = compact ? 720 : 640;
  const height = compact ? 300 : 420;
  const pad = compact ? { l: 128, r: 28, t: 28, b: 40 } : { l: 128, r: 28, t: 28, b: 46 };
  const sleeve = strategy.scale === "sleeve";
  const min = sleeve ? 4900 : SIFT.moneyMin;
  const max = sleeve ? 5200 : SIFT.moneyMax;
  const series = [];
  if (strategy.points.length) {
    series.push({ name: strategy.lineName || (sleeve ? "Primary sleeve" : "Paper account"), color: strategy.color, dash: "", points: strategy.points });
  }
  if (strategy.extra) series.push({ name: strategy.extra.name, color: strategy.extra.color, dash: "7 5", points: strategy.extra.points });
  if (strategy.benchmark && strategy.benchmark.points) {
    series.push({ name: strategy.benchmark.name, color: strategy.benchmark.color, dash: "2 6", points: strategy.benchmark.points });
  }
  const stamp = (point) => point.date + (point.session ? " " + point.session : "");
  const dates = [...new Set(series.flatMap((item) => item.points.map(stamp)))].sort((a, b) => {
    const [aDate, aSession] = a.split(" ");
    const [bDate, bSession] = b.split(" ");
    if (aDate !== bDate) return aDate < bDate ? -1 : 1;
    return (aSession === "close") - (bSession === "close");
  });
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  const labelBits = series.map((item) => item.name + " " + item.points.map((point) => shortDate(point.date) + " " + money(point.equity)).join(" to "));
  svg.setAttribute("aria-label", strategy.name + ". " + labelBits.join(". "));
  const x = (point) => {
    const key = stamp(point);
    if (dates.length < 2) return pad.l + (width - pad.l - pad.r) / 2;
    const index = dates.indexOf(key);
    return pad.l + (index / (dates.length - 1)) * (width - pad.l - pad.r);
  };
  const y = (value) => pad.t + (1 - (value - min) / (max - min)) * (height - pad.t - pad.b);
  const grid = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const mid = Math.round((min + SIFT.capital) / 2 / 100) * 100;
  const ticks = sleeve
    ? (compact ? [4900, 5000, 5200] : [4900, 5000, 5100, 5200])
    : (compact ? [min, SIFT.capital, max] : [min, mid, SIFT.capital, max]);
  const fontSize = compact ? "20" : "16";
  ticks.forEach((tick) => {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", pad.l);
    line.setAttribute("x2", width - pad.r);
    line.setAttribute("y1", y(tick));
    line.setAttribute("y2", y(tick));
    line.setAttribute("class", tick === 10000 || tick === 5000 ? "grid-zero" : "grid-line");
    line.setAttribute("stroke-width", tick === 10000 || tick === 5000 ? "1.5" : "1");
    grid.append(line);
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", 8);
    text.setAttribute("y", tick === ticks[ticks.length - 1] ? y(tick) + 16 : y(tick) + 5);
    text.setAttribute("font-size", fontSize);
    text.textContent = money(tick);
    grid.append(text);
  });
  const xAt = (index) => dates.length < 2
    ? pad.l + (width - pad.l - pad.r) / 2
    : pad.l + (index / (dates.length - 1)) * (width - pad.l - pad.r);
  const minLabelGap = compact ? 96 : 84;
  const labelIndexes = [];
  dates.forEach((key, index) => {
    const edge = index === 0 || index === dates.length - 1;
    if (edge) {
      labelIndexes.push(index);
      return;
    }
    const prev = labelIndexes[labelIndexes.length - 1];
    if (xAt(index) - xAt(prev) < minLabelGap) return;
    if (xAt(dates.length - 1) - xAt(index) < minLabelGap) return;
    labelIndexes.push(index);
  });
  labelIndexes.forEach((index) => {
    const key = dates[index];
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", xAt(index));
    text.setAttribute("y", height - 12);
    const anchor = dates.length < 2 ? "middle" : index === 0 ? "start" : index === dates.length - 1 ? "end" : "middle";
    text.setAttribute("text-anchor", anchor);
    text.setAttribute("font-size", fontSize);
    const [date, session] = key.split(" ");
    text.textContent = shortDate(date) + (session ? " " + session : "");
    grid.append(text);
  });
  svg.append(grid);
  series.forEach((item) => {
    const coords = item.points.map((point) => `${x(point)},${y(point.equity)}`);
    if (coords.length > 1 && stamp(item.points[0]) !== stamp(item.points[1])) {
      const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      poly.setAttribute("fill", "none");
      poly.setAttribute("stroke", item.color);
      poly.setAttribute("stroke-width", "4");
      poly.setAttribute("points", coords.join(" "));
      if (item.dash) poly.setAttribute("stroke-dasharray", item.dash);
      svg.append(poly);
    }
  });
  [...series].reverse().forEach((item) => {
    item.points.forEach((point) => {
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", x(point));
      dot.setAttribute("cy", y(point.equity));
      dot.setAttribute("r", "7");
      dot.setAttribute("fill", item.color);
      svg.append(dot);
    });
  });
  host.append(svg);
}

function legend(strategy) {
  const row = document.createElement("div");
  row.className = "legend";
  const bits = [];
  if (strategy.points.length) bits.push({ name: strategy.lineName || (strategy.scale === "sleeve" ? "Primary sleeve" : "Paper account"), color: strategy.color, dash: false });
  if (strategy.extra) bits.push({ name: strategy.extra.name, color: strategy.extra.color, dash: true });
  if (strategy.benchmark && strategy.benchmark.points) bits.push({ name: strategy.benchmark.name, color: strategy.benchmark.color, dash: true });
  bits.forEach((bit) => {
    const span = document.createElement("span");
    span.innerHTML = `<i class="swatch${bit.dash ? " dash" : ""}" style="border-top-color:${bit.color}"></i>${bit.name}`;
    row.append(span);
  });
  return row;
}

function toneOf(pct) {
  if (pct > 0.05) return { tone: "up", word: "Up" };
  if (pct < -0.05) return { tone: "down", word: "Down" };
  return { tone: "flat", word: "Flat" };
}

function benchPctOf(strategy) {
  if (strategy.benchmark && strategy.benchmark.points && strategy.benchmark.points.length) {
    const last = strategy.benchmark.points[strategy.benchmark.points.length - 1].equity;
    return (last / SIFT.capital - 1) * 100;
  }
  if (strategy.benchmark && Number.isFinite(strategy.benchmark.stated)) return strategy.benchmark.stated;
  return null;
}

function resultOf(strategy) {
  const days = dayCount(strategy.start, strategy.asOf);
  if (strategy.planned) {
    return { word: "Not started", tone: "wait", figure: "—", pct: null, delta: null, latestText: "—", versus: "No paper account yet", days: null, span: "Not started", detail: "No paper account yet" };
  }
  if (strategy.scale === "sleeve") {
    const open = strategy.points[0].equity;
    const close = strategy.points[strategy.points.length - 1].equity;
    const pct = (close / open - 1) * 100;
    const variantOpen = strategy.extra.points[0].equity;
    const variantClose = strategy.extra.points[strategy.extra.points.length - 1].equity;
    const variantPct = (variantClose / variantOpen - 1) * 100;
    const benchPct = benchPctOf(strategy);
    const status = toneOf(pct);
    return {
      word: "Primary",
      tone: status.tone,
      figure: signedPct(pct),
      pct,
      delta: close - open,
      latestText: money(close) + " sleeve",
      versus: versusText(benchPct == null ? null : pct - benchPct),
      span: "Same day · variant " + signedPct(variantPct),
      detail: "Primary " + signedPct(pct) + " · variant " + signedPct(variantPct)
    };
  }
  const pct = (strategy.latest / SIFT.capital - 1) * 100;
  const status = toneOf(pct);
  const benchPct = benchPctOf(strategy);
  const span = days == null ? strategy.asOfLabel : days === 0 ? "Same day" : days + (days === 1 ? " day" : " days") + " tracked";
  return {
    word: status.word,
    tone: status.tone,
    figure: signedPct(pct),
    pct,
    delta: strategy.latest - SIFT.capital,
    latestText: money(strategy.latest),
    versus: versusText(benchPct == null ? null : pct - benchPct),
    span: status.word === "Flat" ? span + " · " + strategy.change : span,
    detail: money(strategy.latest) + (benchPct == null ? "" : " · buy-and-hold " + signedPct(benchPct))
  };
}

function factsHtml(result) {
  return `<dl class="facts">
    <div><dt>Latest</dt><dd>${result.latestText}</dd></div>
    <div><dt>Dollars</dt><dd class="tone-${result.tone}">${signedMoney(result.delta)}</dd></div>
    <div><dt>Span</dt><dd>${result.span}</dd></div>
    <div><dt>Versus hold</dt><dd>${result.versus}</dd></div>
  </dl>`;
}


// ---------- informative layer: hero facts, leaderboard, last-updated stamps (display only; numbers come from data.js) ----------
const MARKET_BY_N = { 1: "Crypto", 2: "Crypto", 3: "Crypto", 4: "Crypto", 5: "Crypto", 6: "Crypto", 7: "Crypto", 8: "Stocks", 9: "Stocks", 10: "ETFs, intraday" };
function marketOf(strategy) {
  if (strategy.regime && strategy.regime.market) return strategy.regime.market === "crypto" ? "Crypto" : "Stocks";
  return MARKET_BY_N[strategy.n] || "—";
}
function maxDrawdownOf(strategy) {
  const pts = strategy.points || [];
  if (pts.length < 2) return pts.length ? 0 : null;
  let peak = -Infinity, worst = 0;
  pts.forEach((p) => { peak = Math.max(peak, p.equity); worst = Math.min(worst, (p.equity / peak - 1) * 100); });
  return worst;
}
function setSum(id, text) {
  const el = document.getElementById(id);
  if (el && text) el.textContent = text;
}
function renderHero() {
  renderStamp();
  renderUpdates();
  const host = document.getElementById("hero-facts");
  if (!host) return;
  const live = SIFT.strategies.filter((s) => !s.planned).length;
  const ranked = SIFT.strategies
    .map((s) => ({ s, r: resultOf(s) }))
    .filter((row) => row.r.pct != null)
    .sort((a, b) => b.r.pct - a.r.pct || a.s.n - b.s.n);
  const best = ranked[0];
  const bestHtml = best
    ? `<a href="strategy.html?n=${best.s.n}">${esc(best.s.name)}</a> <b class="tone-${best.r.tone}">${esc(best.r.figure)}</b>`
    : "—";
  host.innerHTML = `
    <div><dt>Strategies</dt><dd>${SIFT.strategies.length} <small>(${live} running)</small></dd></div>
    <div><dt>Best paper return</dt><dd>${bestHtml}</dd></div>
    <div><dt>Paper per strategy</dt><dd>${money(SIFT.capital).replace(".00", "")}</dd></div>
    <div><dt>Latest mark</dt><dd>${esc(SIFT.asOf)}</dd></div>`;
  const counts = { up: 0, down: 0, flat: 0, wait: 0 };
  SIFT.strategies.forEach((s) => { counts[resultOf(s).tone] += 1; });
  const line = document.getElementById("score-line");
  if (line) line.textContent = counts.up + " up · " + counts.down + " down · " + counts.flat + " flat · " + counts.wait + " not started";
  const kicker = document.getElementById("hero-kicker");
  if (kicker && SIFT.asOf) kicker.textContent = "Daily check-in · " + SIFT.asOf;
}
const LB_COLS = [
  { key: "rank", label: "#", num: true, cls: "col-rank" },
  { key: "name", label: "Strategy", cls: "col-name" },
  { key: "pct", label: "Forward return", num: true, cls: "col-ret" },
  { key: "spark", label: "Path", cls: "col-spark", nosort: true },
  { key: "market", label: "Market", cls: "col-mkt" },
  { key: "delta", label: "Dollars", num: true, cls: "col-dollars" },
  { key: "dd", label: "Max drawdown", num: true, cls: "col-dd" },
  { key: "days", label: "Days live", num: true, cls: "col-days" },
  { key: "gap", label: "Versus hold", num: true, cls: "col-gap" }
];
function earlyFlag(days) {
  if (days == null || days >= 90) return "";
  return `<span class="early-flag">Too early to tell</span>`;
}
function pathSpark(points, tone) {
  const values = (points || []).map((point) => point.equity).filter((n) => Number.isFinite(n));
  if (values.length < 2) return `<span class="spark-empty">—</span>`;
  const samples = downsample(values, 24);
  const min = Math.min.apply(null, samples);
  const max = Math.max.apply(null, samples);
  const span = max - min || 1;
  const width = 88;
  const height = 28;
  const pts = samples.map((value, index) => {
    const x = (index / (samples.length - 1)) * width;
    const y = (height - 3) - ((value - min) / span) * (height - 6);
    return x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  const name = tone === "up" || tone === "down" || tone === "flat" ? tone : "flat";
  return `<svg class="path-spark tone-${name}" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true"><polyline fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round" points="${pts}"/></svg>`;
}
let LB_SORT = { key: "rank", dir: 1 };
function leaderboardRows() {
  return SIFT.strategies.map((s) => {
    const r = resultOf(s);
    const b = benchPctOf(s);
    return { s, r, name: s.name, market: marketOf(s), pct: r.pct, delta: r.delta, dd: s.planned ? null : maxDrawdownOf(s),
      days: s.planned ? null : dayCount(s.start, s.asOf), gap: r.pct == null || b == null ? null : r.pct - b };
  });
}
function renderLeaderboard() {
  const host = document.getElementById("leaderboard-mount");
  if (!host) return;
  const rows = leaderboardRows();
  rows.forEach((x) => { x.rank = x.s.rank == null ? null : x.s.rank; });
  const k = LB_SORT.key, dir = LB_SORT.dir;
  rows.sort((a, b) => {
    const av = a[k], bv = b[k];
    if (av == null && bv == null) return a.s.n - b.s.n;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "string") return dir * av.localeCompare(bv);
    return dir * (av - bv) || a.s.n - b.s.n;
  });
  const tone = (v) => v == null ? "" : v > 0.005 ? "tone-up" : v < -0.005 ? "tone-down" : "tone-flat";
  const sparkTone = (v) => v == null ? "flat" : v > 0.005 ? "up" : v < -0.005 ? "down" : "flat";
  const pts = (v) => v == null ? "—" : (Math.abs(v) < 0.005 ? "even" : (v > 0 ? "+" : "−") + Math.abs(v).toFixed(2) + " pts");
  const head = LB_COLS.map((c) => {
    const arrow = LB_SORT.key === c.key ? (LB_SORT.dir < 0 ? " ▼" : " ▲") : "";
    const inner = c.nosort ? c.label : `<button type="button" data-key="${c.key}" aria-label="Sort by ${c.label}">${c.label}${arrow}</button>`;
    return `<th scope="col" class="${c.cls || ""} ${c.num ? "num-col" : ""}">${inner}</th>`;
  }).join("");
  const body = rows.map((x) => `<tr class="${x.s.stale ? "is-stale" : ""}">
      <td class="num-col col-rank rank-col">${x.rank || "—"}${rankMoveHtml(x.s)}</td>
      <th scope="row" class="col-name"><a href="strategy.html?n=${x.s.n}"><span class="lb-n">${String(x.s.n).padStart(2, "0")}</span> ${esc(x.s.name)}</a>${x.s.label ? " " + labelChip(x.s) : ""}${x.s.isNew ? ' <span class="chip chip-new">New</span>' : ""}<span class="lb-sub">${esc(x.s.category)} · started ${x.s.start ? shortDate(x.s.start) : "—"}${x.s.stale ? " · stale" : ""}</span></th>
      <td class="num-col col-ret ${tone(x.pct)}">${x.pct == null ? "Not started" : `<span class="ret-num">${signedPct(x.pct)}</span>`}${earlyFlag(x.days)}</td>
      <td class="col-spark">${x.s.planned ? `<span class="spark-empty">—</span>` : pathSpark(x.s.points, sparkTone(x.pct))}</td>
      <td class="col-mkt">${esc(x.market)}</td>
      <td class="num-col col-dollars ${tone(x.delta)}">${x.delta == null ? "—" : signedMoney(x.delta)}</td>
      <td class="num-col col-dd">${x.dd == null ? "—" : (x.dd > -0.005 ? "0.00%" : signedPct(x.dd))}</td>
      <td class="num-col col-days">${x.days == null ? "—" : x.days}</td>
      <td class="num-col col-gap ${tone(x.gap)}">${pts(x.gap)}</td>
    </tr>`).join("");
  const tracked = rows.filter((x) => x.days != null);
  const earlyN = tracked.filter((x) => x.days < 90).length;
  const banner = document.getElementById("early-banner");
  if (banner) {
    if (tracked.length && earlyN === tracked.length) banner.textContent = "Forward results: too early to tell. Every running strategy has fewer than 90 days of marks, so this rank is a diary, not a verdict.";
    else if (earlyN) banner.textContent = earlyN + " of " + tracked.length + " forward tests have fewer than 90 days of marks: too early to tell.";
    else banner.textContent = "";
  }
  host.innerHTML = `<div class="section-head lb-head"><div><p class="desk-label">Forward paper</p><h2 id="lb-title">Leaderboard</h2></div><p class="lb-asof">As of ${esc(SIFT.asOf)}</p></div>
    <details class="lb-help"><summary>How this rank works</summary><p>Every strategy ranked best to worst by its forward paper return since its own start date, as of ${esc(SIFT.asOf)}, and re-ranked after every daily update. Arrows show the move versus the previous day's rank${SIFT.rankPrevDay ? " (" + shortDate(SIFT.rankPrevDay) + ")" : ""}; “New” means fewer than 5 days live. Ties go to the lower strategy number; not-started strategies sit at the bottom. Click a column to sort. Max drawdown is the worst drop between recorded daily marks. A forward test under 90 days is marked too early to tell.</p></details>
    <div class="rtable lb-table lb-scroll"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  host.querySelectorAll("thead button").forEach((btn) => btn.addEventListener("click", () => {
    const key = btn.dataset.key;
    LB_SORT = LB_SORT.key === key ? { key, dir: -LB_SORT.dir } : { key, dir: key === "name" || key === "market" || key === "rank" ? 1 : -1 };
    renderLeaderboard();
  }));
}

function renderBacktestBoard() {
  const host = document.getElementById("backtest-board-mount");
  if (!host) return;
  loadBacktestDoc().then((doc) => {
    const partial = new Set((doc.coverage && doc.coverage.partial) || []);
    const ranked = (doc.strategies || []).map((rec) => {
      const view = viewForAll(rec, doc);
      if (!view || view.empty || view.returnPct == null || !Number.isFinite(view.returnPct)) return null;
      return { rec, view };
    }).filter(Boolean).sort((a, b) => b.view.returnPct - a.view.returnPct || a.rec.n - b.rec.n);
    const top = ranked.slice(0, 5);
    if (!top.length) {
      host.innerHTML = `<p class="bt-banner">BACKTEST</p><h2 id="bt-side-title">Top backtested paths</h2><p class="meta">No backtest curve is in this build.</p>`;
      return;
    }
    const cards = top.map(({ rec, view }) => {
      const gap = view.benchReturnPct == null || !Number.isFinite(view.benchReturnPct) ? null : round1(view.returnPct - view.benchReturnPct);
      const toneName = view.returnPct > 0.05 ? "up" : view.returnPct < -0.05 ? "down" : "flat";
      const windowText = (view.startDate && view.endDate) ? isoLong(view.startDate) + " – " + isoLong(view.endDate) : "Window recorded on the curve";
      return `<a class="bt-mini" href="strategy.html?n=${rec.n}#backtest">
        <span class="bt-banner">BACKTEST</span>
        <strong>${esc(rec.name)}</strong>
        <span class="figure ${toneClass(view.returnPct)}">${btPct(view.returnPct)}</span>
        ${pathSpark(view.strat, toneName)}
        <span class="meta">${esc(windowText)}${partial.has(rec.n) ? " · partial window" : ""}</span>
        <span class="meta">Max drawdown ${btPct(view.maxDdPct)}${gap == null ? "" : " · versus " + esc(view.benchName || "benchmark") + " " + btPoints(gap)}</span>
      </a>`;
    }).join("");
    const asOf = doc.meta && (doc.meta.v2generatedET || doc.meta.generatedET);
    host.innerHTML = `<p class="bt-banner">BACKTEST</p><h2 id="bt-side-title">Top backtested paths</h2><p class="meta">Hypothetical, includes costs. Not the forward paper result.${asOf ? " Built " + esc(asOf) + "." : ""}</p><div class="bt-list">${cards}</div>`;
  }).catch(() => {
    host.innerHTML = `<p class="bt-banner">BACKTEST</p><h2 id="bt-side-title">Top backtested paths</h2><p class="meta">Backtests could not be loaded.</p>`;
  });
}

function renderBoard() {
  const board = document.getElementById("board-mount");
  const tally = document.getElementById("tally");
  const counts = { up: 0, down: 0, flat: 0, wait: 0 };
  SIFT.strategies.forEach((strategy) => {
    const result = resultOf(strategy);
    counts[result.tone] += 1;
    const row = document.createElement("article");
    row.className = "strategy-row drawer tone-" + result.tone;
    row.dataset.drawerGroup = "board";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "row-toggle";
    toggle.setAttribute("aria-expanded", "false");
    const rankLabel = strategy.rank ? "#" + strategy.rank : "—";
    toggle.innerHTML = `<span class="row-rank">${rankLabel}${rankMoveHtml(strategy)}</span><span class="row-name">${esc(strategy.name)}</span><span class="row-pnl tone-${result.tone}">${esc(result.figure)}</span><span class="fold-chevron" aria-hidden="true"></span>`;
    const link = document.createElement("a");
    link.className = "card tone-" + result.tone;
    link.href = "strategy.html?n=" + strategy.n;
    link.target = "sift-" + strategy.n;
    link.addEventListener("click", (event) => {
      if (window.matchMedia("(max-width: 768px)").matches) return;
      event.preventDefault();
      window.open(link.href, link.target, "popup=yes,width=860,height=940,resizable=yes,scrollbars=yes");
    });
    const top = document.createElement("div");
    top.className = "card-top";
    const rankBadge = strategy.rank ? `<span class="rank-badge" title="Rank by forward return">#${strategy.rank}${rankMoveHtml(strategy)}${strategy.isNew ? '<em>New</em>' : ""}</span>` : `<span class="rank-badge rank-none">Not ranked</span>`;
    top.innerHTML = `<span class="num">${rankBadge}${String(strategy.n).padStart(2, "0")} · ${strategy.category}</span>${strategy.label ? labelChip(strategy) : `<span class="tag">${strategy.tag}</span>`}`;
    const title = document.createElement("h2");
    title.textContent = strategy.name;
    const plain = document.createElement("p");
    plain.className = "plain";
    plain.textContent = strategy.plain;
    const resultRow = document.createElement("div");
    resultRow.className = "result";
    const daysLive = strategy.planned ? null : dayCount(strategy.start, strategy.asOf);
    resultRow.innerHTML = `<span class="figure">${result.figure}</span><span class="status">${result.word}</span>${earlyFlag(daysLive)}`;
    const facts = document.createElement("div");
    facts.innerHTML = factsHtml(result);
    link.append(top, title, plain, resultRow, facts.firstElementChild);
    if (strategy.planned) {
      const empty = document.createElement("div");
      empty.className = "empty-plot";
      empty.textContent = "Not launched. No marks to plot.";
      link.append(empty);
    } else {
      const plot = document.createElement("div");
      plot.className = "plot";
      drawChart(plot, strategy, { compact: true });
      link.append(plot, legend(strategy));
    }
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = strategy.planned ? result.detail : strategy.asOfLabel;
    link.append(meta);
    row.append(toggle, link);
    board.append(row);
  });
  if (tally) {
    const bits = [
      ["up", counts.up, "Up"],
      ["down", counts.down, "Down"],
      ["flat", counts.flat, "Flat"],
      ["wait", counts.wait, "Not started"]
    ];
    tally.innerHTML = bits.map(([tone, count, label]) => `<article class="tone-${tone}"><strong>${count}</strong><span>${label}</span></article>`).join("");
  }
  renderRegime();
  renderMood();
  renderPositions();
  renderTicker();
  renderHero();
  renderLeaderboard();
  renderBacktestBoard();
  const book = document.getElementById("book-mount");
  const ladder = document.getElementById("ladder-mount");
  const priced = SIFT.strategies.filter((item) => item.latest != null);
  const base = priced.length * SIFT.capital;
  const sum = priced.reduce((total, item) => total + item.latest, 0);
  const ranked = SIFT.strategies
    .map((item) => ({ item, result: resultOf(item) }))
    .filter((row) => row.result.pct != null)
    .sort((a, b) => b.result.pct - a.result.pct || a.item.n - b.item.n);
  const best = ranked[0];
  const worst = ranked[ranked.length - 1];
  if (book && best && worst) {
    const bookPct = (sum / base - 1) * 100;
    const bookTone = toneOf(bookPct).tone;
    book.innerHTML = `
      <h2 class="fold-dup">Paper balances</h2>
      <article class="tone-${bookTone}"><span>${priced.length} paper balances</span><strong>${money(sum)}</strong><p>${signedMoney(sum - base)} · ${signedPct(bookPct)} from ${money(base)}. SEASONS is not started. The day-trade line uses its primary account.</p></article>
      <article class="tone-${best.result.tone}"><span>Best recorded</span><strong>${best.result.figure}</strong><p>${best.item.name}. ${signedMoney(best.result.delta)}.</p></article>
      <article class="tone-${worst.result.tone}"><span>Worst recorded</span><strong>${worst.result.figure}</strong><p>${worst.item.name}. ${signedMoney(worst.result.delta)}.</p></article>`;
  }
  if (ladder) {
    const scale = 8;
    const rows = ranked.map(({ item, result }) => {
      const width = Math.min(50, Math.abs(result.pct) / scale * 50);
      const left = result.pct >= 0 ? 50 : 50 - width;
      return `<li><span class="who">${String(item.n).padStart(2, "0")} ${item.name}</span><span class="track"><i style="left:${left}%;width:${width}%;background:${item.color}"></i></span><b class="tone-${result.tone}">${result.figure}</b></li>`;
    }).join("");
    ladder.innerHTML = `<h2 class="fold-dup">Recorded change from the start</h2><ol>${rows}</ol>`;
  }
  const maxN = Math.max(...SIFT.strategies.map((item) => item.n));
  const open = (3 - (SIFT.strategies.length % 3)) % 3;
  for (let slot = maxN + 1; slot <= maxN + open; slot += 1) {
    const cell = document.createElement("article");
    cell.className = "slot";
    cell.innerHTML = `<div class="slot-top"><span class="num">${slot}</span><span class="tag">Open</span></div><h2>Room for a later test</h2><div class="empty-plot">Empty on purpose. A new strategy can be added here.</div>`;
    board.append(cell);
  }
  if (best) setSum("leaderboard-sum", "#" + (best.item.rank || "—") + " " + best.item.name + " " + best.result.figure);
  setSum("board-sum", SIFT.strategies.length + " strategies");
  if (SIFT.regime) {
    const parts = [];
    if (SIFT.regime.stock) parts.push("Stocks " + regimeName(SIFT.regime.stock.regime));
    if (SIFT.regime.crypto) parts.push("Crypto " + regimeName(SIFT.regime.crypto.regime));
    const label = parts.join(" · ");
    setSum("mood-sum", label);
    setSum("regime-sum", label);
  }
  let held = 0;
  let cashN = 0;
  SIFT.strategies.forEach((s) => {
    const cells = positionCells(s);
    if (cells.some((c) => c.kind === "symbol" || c.kind === "open")) held += 1;
    else if (cells.some((c) => c.kind === "cash")) cashN += 1;
  });
  setSum("positions-sum", held + " holding · " + cashN + " in cash");
  if (best && worst) {
    setSum("book-sum", money(sum) + " combined");
    setSum("ladder-sum", best.result.figure + " best · " + worst.result.figure + " worst");
  }
  const newest = (SIFT.updates || [])[0];
  setSum("updates-sum", newest ? newest.title : "Daily log");
}

const REGIME_TEXT = {
  trend_up: { name: "Trend up", stocks: "Rising: above the 50- and 200-day averages, and up over the last 3 months.", crypto: "Rising: above the 50- and 200-day averages, and up over the last 3 months." },
  range: { name: "Range", stocks: "Sideways: no clear trend either way.", crypto: "Sideways: no clear trend either way." },
  risk_off: { name: "Risk-off", stocks: "Under the 50-day average while bonds and gold lead stocks.", crypto: "Under the 50-day average while stocks are weak." },
  trend_down: { name: "Trend down", stocks: "Falling: under the 200-day average, and the 50-day is under the 200-day.", crypto: "Falling: under the 200-day average, and the 50-day is under the 200-day." },
  shock: { name: "Shock", stocks: "A volatility spike with a sharp drop from the 20-day high.", crypto: "A volatility spike with a sharp drop from the 20-day high." }
};
const REGIME_ORDER = ["trend_up", "range", "risk_off", "trend_down", "shock"];
function regimeName(key) { return (REGIME_TEXT[key] || { name: key || "n/a" }).name; }

function labelChip(strategy) {
  const proven = strategy.label === "proven in backtest";
  const risk = strategy.riskLevel ? `<span class="chip chip-aggr" title="High-risk strategy: large drawdowns in its backtest">${strategy.riskLevel}</span>` : "";
  return `<span class="chips"><span class="chip ${proven ? "chip-proven" : "chip-hybrid"}">${proven ? "Proven in backtest" : "New forward-test hybrid"}</span>${risk}</span>`;
}

function regimeFitToday(strategy) {
  const reg = SIFT.regime && strategy.regime ? SIFT.regime[strategy.regime.market === "crypto" ? "crypto" : "stock"] : null;
  if (!reg) return null;
  const r = strategy.regime;
  if ((r.sitOutList || []).includes(reg.regime)) return "sit";
  if ((r.bestList || []).includes(reg.regime)) return "best";
  return "neutral";
}

function renderRegime() {
  const host = document.getElementById("regime-mount");
  if (!host || !SIFT.regime) return;
  const pill = (key, label, market) => {
    const r = SIFT.regime[key];
    if (!r) return "";
    const t = REGIME_TEXT[r.regime] || { name: r.regime, stocks: "", crypto: "" };
    return `<article class="regime-pill reg-${r.regime}">
      <span class="regime-market">${label}</span>
      <strong>${t.name}</strong>
      <p>${t[market]}</p>
      <p class="meta">${r.asset} close ${r.close.toLocaleString("en-US")} on ${shortDate(r.date)} · 50-day ${r.sma50.toLocaleString("en-US")} · 200-day ${r.sma200.toLocaleString("en-US")} · 3-month ${signedPct(r.ret63)} · volatility ${r.vol_ratio}× normal</p>
    </article>`;
  };
  const rows = SIFT.strategies.filter((s) => s.regime && s.label);
  const best = rows.filter((s) => regimeFitToday(s) === "best");
  const sit = rows.filter((s) => regimeFitToday(s) === "sit");
  const list = (items) => items.length ? items.map((s) => `<a href="strategy.html?n=${s.n}">${String(s.n).padStart(2, "0")} ${s.name}</a>`).join(" · ") : "None";
  host.innerHTML = `<h2 class="fold-dup">Current market regime</h2>
    <p class="regime-intro">What kind of market are we in today? Each strategy works best in some conditions and steps aside in others. This label is worked out each day from closing prices for stocks (SPY) and crypto (BTC).</p>
    <div class="regime-grid">${pill("stock", "Stocks · SPY", "stocks")}${pill("crypto", "Crypto · BTC", "crypto")}</div>
    <p class="regime-fit"><b>In their best regime today:</b> ${list(best)}</p>
    <p class="regime-fit"><b>Sitting out today:</b> ${list(sit)}</p>
    <details class="regime-legend"><summary>What the five regimes mean</summary><ul>${REGIME_ORDER.map((k) => `<li><b class="reg-word reg-${k}">${REGIME_TEXT[k].name}</b> ${REGIME_TEXT[k].stocks}${k === "risk_off" ? " For crypto: under the 50-day average while stocks are weak." : ""}${k === "shock" ? " The drop threshold is 7% for SPY and 15% for BTC." : ""}</li>`).join("")}</ul><p>Why it matters: each new strategy lists the regimes where it did best in its backtest and the ones where it steps aside. The label is checked in this order: shock, trend down, risk-off, trend up, range.</p></details>
    <p class="meta">A daily label from closing prices only. Updated ${SIFT.regime.asOf}. It describes the market; it is not a forecast.</p>`;
}

function regimeFitHtml(strategy) {
  if (!strategy.regime) return "";
  const r = strategy.regime;
  const market = r.market === "crypto" ? "crypto" : "stock";
  const today = SIFT.regime && SIFT.regime[market];
  const rowsHtml = REGIME_ORDER.map((key) => {
    const v = (r.annualizedByRegime || {})[key];
    const tone = v == null ? "" : v > 0.05 ? "tone-up" : v < -0.05 ? "tone-down" : "tone-flat";
    const marks = [(r.bestList || []).includes(key) ? "best" : "", (r.sitOutList || []).includes(key) ? "sit out" : "", today && today.regime === key ? "today" : ""].filter(Boolean).join(" · ");
    return `<tr${today && today.regime === key ? ' class="is-today"' : ""}><th>${regimeName(key)}</th><td class="${tone}">${v == null ? "—" : signedPct(v)}</td><td>${marks}</td></tr>`;
  }).join("");
  return `<h2 class="fold-dup">Market regime fit</h2>
    <p>Best regime: ${r.best}. Sit out: ${r.sitOut}.${today ? ` Today (${today.asset}, ${shortDate(today.date)}): <b>${regimeName(today.regime)}</b>.` : ""}</p>
    <div class="rtable"><table><thead><tr><th>Regime</th><th>Backtest annualized return</th><th></th></tr></thead><tbody>${rowsHtml}</tbody></table></div>
    <p class="meta">Historical backtest by regime (new experiment, Nov 10, 2026). Separate from the forward paper result above.</p>`;
}

function whyHtml(strategy) {
  const why = strategy.why;
  if (!why || !why.text) return `<h2 class="fold-dup">Why we picked this</h2><p>No note recorded.</p>`;
  const flag = why.hasRecord ? "Original backtest on record" : "No original backtest record for these exact rules";
  return `<h2 class="fold-dup">Why we picked this</h2><div class="why-box"><p class="preview"><span>${flag}</span></p><p>${why.text}</p>${why.records && why.records.length ? `<p class="meta">Records: ${why.records.join(" · ")}</p>` : ""}</div>`;
}

const COPY_DISCLAIMER = "Educational paper-trading rules, not financial advice or a recommendation to buy or sell. Past and backtested results don't guarantee future returns.";
const NOT_STATED = "Not stated in the published rules.";
const ENTRY_RE = /\b(buy|buys|enter|entry|long an|long while|hold when|hold while|hold the|hold 100|holds the|signal when|signal:|new buys|rank by|score =|owns bitcoin|own bitcoin)\b/i;
const EXIT_RE = /\b(sell|sold|exit|exits|stop|goes to cash|hold cash|in cash|otherwise flat|otherwise cash|flat overnight|flat by the close|time stop|drop out|below it)\b/i;
const SIZE_RE = /(\$[\d,]+|\bone third\b|\bone fifth\b|\bone tenth\b|\bone half\b|equal weight|full sleeve|all-in|\bslots\b|per position|per coin|per asset|\bweight\b|up to \d+|maximum \d+|\b100%\b|\d+%)/i;
const TIME_RE = /\b(rebalance|month-end|every \d+|each (day|week|month)|weekly|daily check|fill at|filled at|signal at the close|last trading day|next (daily |trading |utc |bar))/i;

function uniqueLines(lines) {
  const out = [];
  (lines || []).forEach((line) => {
    const text = String(line || "").trim();
    if (text && !out.includes(text)) out.push(text);
  });
  return out;
}
function matchingLines(lines, re) {
  return lines.filter((line) => re.test(line));
}
function stepHtml(lines) {
  const items = uniqueLines(lines);
  if (!items.length) return `<p>${esc(NOT_STATED)}</p>`;
  if (items.length === 1) return `<p>${esc(items[0])}</p>`;
  return `<ul class="rules">${items.map((line) => `<li>${esc(line)}</li>`).join("")}</ul>`;
}
function stepText(label, lines) {
  const items = uniqueLines(lines);
  if (!items.length) return label + "\n" + NOT_STATED;
  return label + "\n" + items.map((line) => "- " + line).join("\n");
}
function entryLines(strategy, lines) {
  const hit = matchingLines(lines, ENTRY_RE);
  if (hit.length) return hit;
  if (strategy.plain) return ["Published summary: " + strategy.plain];
  return [];
}
function sizingLines(strategy, lines) {
  const hit = matchingLines(lines, SIZE_RE);
  if (strategy.universe && SIZE_RE.test(strategy.universe)) hit.push(strategy.universe);
  return uniqueLines(hit);
}
function timingLines(strategy, lines) {
  const hit = matchingLines(lines, TIME_RE);
  [strategy.universe, strategy.window].forEach((text) => {
    if (text && /\b(rebalance|daily check|weekly|monthly|month-end|every \d+)/i.test(text)) hit.push(text);
  });
  return uniqueLines(hit);
}
function regimeLines(strategy, lines) {
  const hit = [];
  if (strategy.regime) {
    if (strategy.regime.best) hit.push("Best regime, as published: " + strategy.regime.best);
    if (strategy.regime.sitOut) hit.push("Sit out, as published: " + strategy.regime.sitOut);
    if (strategy.regime.market) hit.push("Market: " + strategy.regime.market);
  }
  return uniqueLines(hit.concat(matchingLines(lines, /\bregime\b/i)));
}
function holdingsLines(strategy) {
  const cells = positionCells(strategy);
  const lines = [];
  if (strategy.asOfLabel) lines.push("Published " + strategy.asOfLabel + ".");
  else if (strategy.asOf) lines.push("As of " + strategy.asOf + ".");
  const symbols = cells.filter((c) => c.kind === "symbol").map((c) => c.symbol);
  if (symbols.length) lines.push("Held: " + symbols.join(", ") + ".");
  cells.forEach((cell) => {
    if (cell.kind === "cash") {
      lines.push("Cash. Nothing is held at this mark.");
      if (cell.queued && cell.queued.length) lines.push("Queued for the next close: " + cell.queued.join(", ") + ".");
      if (cell.note) lines.push(cell.note);
    } else if (cell.kind === "open") lines.push(cell.count + " positions open. The published note does not name the symbols.");
    else if (cell.kind === "idle") lines.push("Not started. No paper account yet.");
    else if (cell.kind === "unknown") lines.push("Holdings are not listed in the published forward note.");
  });
  if (strategy.forward) lines.push("Published forward note: " + strategy.forward);
  return uniqueLines(lines);
}
function holdingsSummary(strategy) {
  const cells = positionCells(strategy);
  if (cells.some((c) => c.kind === "idle")) return "Not started";
  const symbols = cells.filter((c) => c.kind === "symbol").map((c) => c.symbol);
  if (symbols.length) return symbols.join(", ");
  const open = cells.find((c) => c.kind === "open");
  if (open) return open.label;
  const cash = cells.find((c) => c.kind === "cash");
  if (cash) return cash.queued && cash.queued.length ? "Cash, queued " + cash.queued.join(", ") : "Cash";
  return "Holdings not listed";
}
function slugName(value) {
  return String(value || "strategy").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "strategy";
}
function downloadText(filename, text) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
function foldBlock(id, group, title, sum, inner) {
  return `<section class="fold" id="${id}" data-fold-group="${group}"><h2 class="fold-heading"><button type="button" class="fold-toggle" aria-expanded="false" aria-controls="${id}-panel"><span class="fold-name">${esc(title)}</span><span class="fold-sum">${esc(sum)}</span><span class="fold-chevron" aria-hidden="true"></span></button></h2><div class="fold-body" id="${id}-panel"><div class="fold-inner">${inner}</div></div></section>`;
}
function copyPack(strategy) {
  const lines = uniqueLines(strategy.rules || []);
  const trades = strategy.universe ? [strategy.universe] : [];
  const entry = entryLines(strategy, lines);
  const exit = matchingLines(lines, EXIT_RE);
  const sizing = sizingLines(strategy, lines);
  const timing = timingLines(strategy, lines);
  const regime = regimeLines(strategy, lines);
  const held = holdingsLines(strategy);
  const how = "Use any broker's paper or simulated account, and start small. Follow only the rules printed here. A broker's simulator will not match these fills exactly. SIFT places no orders.";
  const heldLine = held.find((line) => line.indexOf("Held: ") === 0);
  const rest = held.filter((line) => line.indexOf("Held: ") !== 0);
  const chips = heldLine
    ? `<ul class="hold-list">${heldLine.replace(/^Held: /, "").replace(/\.$/, "").split(", ").map((sym) => `<li>${esc(sym)}</li>`).join("")}</ul>`
    : "";
  const html = `
    <p class="block-kicker">Plain steps from the fields already published for this strategy. A missing detail stays missing. The full rules are listed underneath.</p>
    <dl class="copy-steps">
      <div><dt>What it trades</dt><dd>${stepHtml(trades)}</dd></div>
      <div><dt>Entry signal</dt><dd>${stepHtml(entry)}</dd></div>
      <div><dt>Exit signal</dt><dd>${stepHtml(exit)}</dd></div>
      <div><dt>Position sizing</dt><dd>${stepHtml(sizing)}</dd></div>
      <div><dt>Rebalance timing</dt><dd>${stepHtml(timing)}</dd></div>
      <div><dt>Market-regime filter</dt><dd>${stepHtml(regime)}</dd></div>
    </dl>
    <h3 class="fold-dup">Published rules</h3>
    ${lines.length ? `<ul class="rules">${lines.map((rule) => `<li>${esc(rule)}</li>`).join("")}</ul>` : `<p>${esc(NOT_STATED)}</p>`}
    <h3>Current holdings</h3>
    ${chips}
    ${rest.length ? stepHtml(rest) : (chips ? "" : stepHtml([]))}
    <div class="copy-actions">
      <button type="button" id="copy-rules">Copy rules</button>
      <button type="button" id="download-rules">Download rules (.txt)</button>
      <p class="copy-status" id="copy-status" role="status"></p>
    </div>
    <div class="why-box"><p><b>How to paper-trade this yourself.</b> ${esc(how)}</p></div>
    <p class="disclaimer-line">${esc(COPY_DISCLAIMER)}</p>`;
  const text = [
    "SIFT strategy " + String(strategy.n).padStart(2, "0") + " — " + strategy.name,
    COPY_DISCLAIMER,
    "",
    stepText("What it trades", trades),
    "",
    stepText("Entry signal", entry),
    "",
    stepText("Exit signal", exit),
    "",
    stepText("Position sizing", sizing),
    "",
    stepText("Rebalance timing", timing),
    "",
    stepText("Market-regime filter", regime),
    "",
    "Published rules",
    lines.length ? lines.map((rule, i) => (i + 1) + ". " + rule).join("\n") : NOT_STATED,
    "",
    stepText("Current holdings", held),
    "",
    "How to paper-trade this yourself",
    how,
    "",
    COPY_DISCLAIMER
  ].join("\n");
  return { html, text };
}

function renderStrategy() {
  const params = new URLSearchParams(location.search);
  const strategy = SIFT.strategies.find((item) => item.n === Number(params.get("n")));
  const root = document.getElementById("detail");
  if (!strategy) {
    root.textContent = "That strategy is not on the board.";
    return;
  }
  renderStamp();
  document.title = strategy.name + " · SIFT";
  const result = resultOf(strategy);
  const daysLive = strategy.planned ? null : dayCount(strategy.start, strategy.asOf);
  const plot = strategy.planned ? `<div class="empty-plot">Not launched. No marks to plot.</div>` : `<div class="plot" id="detail-plot"></div>`;
  const pack = copyPack(strategy);
  const backtestTitle = strategy.label ? "Backtest, historical (separate from the forward paper)" : "Backtest, in-sample";
  root.innerHTML = `
    <p class="eyebrow">Strategy ${String(strategy.n).padStart(2, "0")} · ${esc(strategy.category)}</p>
    ${strategy.label ? `<p class="chip-row">${labelChip(strategy)}</p>` : ""}
    <h1>${esc(strategy.name)}</h1>
    <p class="lede">${esc(strategy.plain)}</p>
    ${foldBlock("forward", "strategy", "Forward paper results", result.figure + " · " + result.word + (daysLive != null && daysLive < 90 ? " · too early to tell" : ""), `
      <section class="result-block forward-block" aria-labelledby="forward-heading">
        <h2 id="forward-heading" class="fold-dup">Forward paper results</h2>
        <p class="block-kicker">Simulated account from the daily paper test. Separate from the historical backtest below.</p>
        <p class="result tone-${result.tone}"><span class="figure">${esc(result.figure)}</span><span class="status">${esc(result.word)}</span>${earlyFlag(daysLive)}</p>
        ${factsHtml(result)}
        <p class="scale-note">${esc(result.detail)}. ${esc(strategy.window)} ${esc(strategy.sleeveNote || "Each dot is one recorded daily mark from the paper-test records. Days without a mark are not drawn.")}</p>
        ${plot}
      </section>`)}
    ${foldBlock("copy-strategy", "strategy", "Copy this strategy", holdingsSummary(strategy), pack.html)}
    ${foldBlock("backtest", "strategy", "Backtest by year", "Hypothetical, with costs", `
      <section class="result-block backtest-block" id="backtest-panel" aria-labelledby="backtest-heading">
        <h2 id="backtest-heading" class="fold-dup">Backtest performance</h2>
        <p class="backtest-banner">Backtest (hypothetical, includes costs)</p>
        <p class="block-kicker" id="backtest-method">Loading historical backtest…</p>
        <div id="backtest-body"></div>
      </section>`)}
    ${foldBlock("why", "strategy", "Why we picked this", strategy.why && strategy.why.hasRecord ? "Original backtest on record" : "Note from the published record", whyHtml(strategy))}
    ${foldBlock("hypothesis", "strategy", "What it is testing", "The idea behind the rules", `<h2 class="fold-dup">What it is testing</h2><p>${esc(strategy.hypothesis)}</p>`)}
    ${foldBlock("rules", "strategy", "Rules", (strategy.rules || []).length + " published lines", `<h2 class="fold-dup">Rules</h2><ul class="rules">${(strategy.rules || []).map((rule) => `<li>${esc(rule)}</li>`).join("")}</ul>`)}
    ${strategy.regime ? foldBlock("regime-fit", "strategy", "Market regime fit", "Best and sit-out regimes", regimeFitHtml(strategy)) : ""}
    ${foldBlock("backtest-note", "strategy", "Historical backtest", "Separate from the forward paper", `<h2 class="fold-dup">${esc(backtestTitle)}</h2><p>${esc(strategy.backtest)}</p>`)}
    ${foldBlock("forward-note", "strategy", "Forward paper", strategy.asOfLabel || "The running account", `<h2 class="fold-dup">Forward paper</h2><p>${esc(strategy.forward)}</p>`)}
    ${foldBlock("risk", "strategy", "Main risk", "What can go wrong", `<h2 class="fold-dup">Main risk</h2><p>${esc(strategy.risk)}</p>
      ${strategy.label ? `<p class="fine">Backtest = new experiment dated ${strategy.n >= 18 ? "Nov 11, 2026" : "Nov 10, 2026"}.${strategy.riskLevel ? " Aggressive: expect very large drawdowns; 3x ETFs reset daily and lose value in choppy markets." : ""} Universe is today's list of large stocks/coins, so results carry survivorship bias. Halves are a stability check; parameters were not tuned. “Proven in backtest” means it passed the historical checks only; nothing is proven going forward. Forward paper only, not a forecast.</p>` : ""}
      <p class="fine">Paper only. Simulated $10,000. No live orders. Not financial advice. None of these strategies is proven. Source: ${esc(SIFT.source)}, ${esc(SIFT.asOf)}.</p>`)}
  `;
  const host = document.getElementById("detail-plot");
  if (host) {
    drawChart(host, strategy);
    host.after(legend(strategy));
  }
  mountBacktest(strategy);
  const status = document.getElementById("copy-status");
  const copyBtn = document.getElementById("copy-rules");
  const downloadBtn = document.getElementById("download-rules");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const done = () => { if (status) status.textContent = "Copied."; };
      const fail = () => { if (status) status.textContent = "Could not copy. Use the download."; };
      if (window.siftChrome && window.siftChrome.copyText) window.siftChrome.copyText(pack.text).then(done, fail);
      else fail();
    });
  }
  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      downloadText("sift-" + String(strategy.n).padStart(2, "0") + "-" + slugName(strategy.name) + ".txt", pack.text);
      if (status) status.textContent = "Download started.";
    });
  }
}


/* ---------- Last-updated stamp and Updates log ---------- */
function esc(t) { return String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function renderStamp() {
  const host = document.getElementById("updated-stamp");
  if (host && SIFT.lastUpdatedISO) {
    const ageDays = (Date.now() - Date.parse(SIFT.lastUpdatedISO)) / 86400000;
    const stale = ageDays > 2;
    host.classList.toggle("stale", stale);
    host.innerHTML = `<b id="stamp-when">Last updated: ${esc(SIFT.lastUpdatedET)}</b>` +
      (stale ? `<span class="stamp-stale">Stale: no new data for ${Math.floor(ageDays)} days</span>` : "") +
      `<span class="stamp-next">Next update: ${esc(SIFT.nextUpdate || "daily after the market close (about 8:30 PM ET)")}</span><a href="updates.html">All updates →</a>`;
  }
  const foot = document.getElementById("footer-updated");
  if (foot && SIFT.asOf) foot.textContent = "Latest mark " + SIFT.asOf + (SIFT.builtAt ? ". Board built " + SIFT.builtAt + "." : ".");
}
function updateEntryHtml(e) {
  const tag = e.kind === "milestone" ? `<span class="chip chip-milestone">Milestone</span>` : `<span class="chip chip-daily">Daily</span>`;
  return `<article class="update-entry update-${e.kind} drawer" data-drawer-group="updates">
    <button type="button" class="row-toggle" aria-expanded="false"><span class="row-name">${esc(e.title)}</span>${tag}<span class="fold-chevron" aria-hidden="true"></span></button>
    <div class="drawer-body"><header class="drawer-desk"><time datetime="${esc(e.date)}">${esc(e.title)}</time>${tag}</header>
    <ul>${(e.items || []).map((i) => `<li>${esc(i)}</li>`).join("")}</ul>${e.updatedET ? `<p class="meta">Recorded ${esc(e.updatedET)}</p>` : ""}</div></article>`;
}
function renderUpdates() {
  const host = document.getElementById("updates-mount");
  if (!host || !SIFT.updates) return;
  host.innerHTML = `<div class="section-head"><h2>Latest updates</h2><p>The board refreshes once a day after the market close. Each day's trades, biggest movers and market regime are logged here, newest first.</p></div>
    <div class="updates-list">${SIFT.updates.slice(0, 3).map(updateEntryHtml).join("")}</div>
    <p class="updates-more"><a href="updates.html">See all ${SIFT.updates.length} updates →</a></p>`;
}
function renderUpdatesPage() {
  renderStamp();
  const root = document.getElementById("updates-page");
  if (!root) return;
  document.title = "Updates · SIFT";
  root.innerHTML = `<p class="eyebrow">Updates log</p><h1>What changed, day by day</h1>
    <p class="lede">Newest first. A short entry is added automatically after each daily run (about 8:30 PM ET); milestones mark new strategies and design changes. The last ${SIFT.updates ? SIFT.updates.length : 0} entries are kept.</p>
    <div class="updates-list">${(SIFT.updates || []).map(updateEntryHtml).join("")}</div>
    <p class="fine">Paper only. Simulated $10,000 accounts. No live orders. Not financial advice.</p>`;
}

function rankMoveHtml(s) {
  if (!s || s.rank == null) return "";
  if (s.rankMove == null) return s.prevRank == null && SIFT.rankPrevDay ? ` <span class="rank-move rm-new" title="Not ranked on the previous day">•</span>` : "";
  if (s.rankMove > 0) return ` <span class="rank-move rm-up" title="Up ${s.rankMove} since the previous day">▲${s.rankMove}</span>`;
  if (s.rankMove < 0) return ` <span class="rank-move rm-down" title="Down ${-s.rankMove} since the previous day">▼${-s.rankMove}</span>`;
  return ` <span class="rank-move rm-same" title="Same rank as the previous day">=</span>`;
}

/* ---------- Historical backtest by year (separate from forward paper marks) ---------- */
const BACKTEST_YEARS = ["2020", "2021", "2022", "2023", "2024", "2025", "2026"];
const TRADE_COUNT_LABEL = {
  closed_exits: "closed trades",
  fills: "fills",
  flat_to_flat_episodes: "round trips"
};
let backtestDocPromise = null;

function loadBacktestDoc() {
  if (!backtestDocPromise) {
    const src = (document.querySelector('script[src*="app.js"]') || {}).src || "";
    const version = (src.match(/[?&]v=([^&]+)/) || [])[1] || "1";
    backtestDocPromise = fetch("data/backtest_by_year.json?v=" + encodeURIComponent(version)).then((response) => {
      if (!response.ok) throw new Error("Backtest file could not be loaded (" + response.status + ").");
      return response.json();
    });
  }
  return backtestDocPromise;
}

function isoLong(iso) {
  if (!iso) return "";
  const [year, month, day] = iso.split("-").map(Number);
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return names[month - 1] + " " + day + ", " + year;
}

function btPct(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return sign + Math.abs(value).toFixed(1) + "%";
}

function btPoints(value) {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return sign + Math.abs(value).toFixed(1) + " points";
}

function toneClass(value) {
  if (value == null || !Number.isFinite(value)) return "";
  if (value > 0.05) return "tone-up";
  if (value < -0.05) return "tone-down";
  return "tone-flat";
}

function round1(value) {
  return Math.round(value * 10) / 10;
}

function pointsInRange(points, startDate, endDate) {
  return (points || []).filter((point) => point[0] >= startDate && point[0] <= endDate);
}

function priorPoint(points, startDate) {
  let prior = null;
  for (const point of points || []) {
    if (point[0] < startDate) prior = point;
    else break;
  }
  return prior;
}

function rebaseSlice(points, startDate, endDate, base) {
  if (!base) return [];
  const scale = 10000 / base;
  return pointsInRange(points, startDate, endDate).map(([date, equity]) => ({ date, equity: equity * scale }));
}

function blendHalf(spyPoints, qqqPoints, startDate, endDate) {
  const spy = rebaseSlice(spyPoints, startDate, endDate, (pointsInRange(spyPoints, startDate, endDate)[0] || [])[1]);
  const qqq = rebaseSlice(qqqPoints, startDate, endDate, (pointsInRange(qqqPoints, startDate, endDate)[0] || [])[1]);
  const spyMap = new Map(spy.map((point) => [point.date, point.equity]));
  const qqqMap = new Map(qqq.map((point) => [point.date, point.equity]));
  const dates = [...new Set([...spyMap.keys(), ...qqqMap.keys()])].sort();
  let lastSpy = null;
  let lastQqq = null;
  const out = [];
  dates.forEach((date) => {
    if (spyMap.has(date)) lastSpy = spyMap.get(date);
    if (qqqMap.has(date)) lastQqq = qqqMap.get(date);
    if (lastSpy == null || lastQqq == null) return;
    out.push({ date, equity: (lastSpy + lastQqq) / 2 });
  });
  return out;
}

function maxDrawdownPct(values) {
  let peak = -Infinity;
  let worst = 0;
  values.forEach((value) => {
    if (!Number.isFinite(value) || value <= 0) return;
    peak = Math.max(peak, value);
    worst = Math.min(worst, (value / peak - 1) * 100);
  });
  return peak === -Infinity ? null : worst;
}

function benchSeriesFor(rec, doc, startDate, endDate, shared2019) {
  if (rec.benchmark === "SPY_QQQ_50_50") {
    const spy = doc.benchmarks && doc.benchmarks.SPY && doc.benchmarks.SPY.equityFrom2020;
    const qqq = doc.benchmarks && doc.benchmarks.QQQ && doc.benchmarks.QQQ.equityFrom2020;
    if (!spy || !qqq) return { points: [], name: "50/50 SPY and QQQ buy-and-hold" };
    return { points: blendHalf(spy.points, qqq.points, startDate, endDate), name: "50/50 SPY and QQQ buy-and-hold" };
  }
  const bench = doc.benchmarks && doc.benchmarks[rec.benchmark];
  if (!bench || !bench.equityFrom2020) return { points: [], name: "Buy-and-hold" };
  const points = bench.equityFrom2020.points || [];
  if (shared2019) {
    return { points: pointsInRange(points, startDate, endDate).map(([date, equity]) => ({ date, equity })), name: bench.name };
  }
  const slice = pointsInRange(points, startDate, endDate);
  const prior = priorPoint(points, startDate);
  const base = prior ? prior[1] : (slice[0] && slice[0][1]);
  return { points: rebaseSlice(points, startDate, endDate, base), name: bench.name };
}

function uses2019Anchor(equity) {
  if (!equity || !equity.points || !equity.points.length) return false;
  return equity.startDate <= "2020-01-15" && Math.abs(equity.points[0][1] - (equity.start || 10000)) > 0.02;
}

function caveatsHtml(rec) {
  const items = rec.caveats || [];
  if (!items.length) return "";
  return `<ul class="bt-caveats">${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
}

function sentence(label, value) {
  if (!value) return "";
  const text = String(value).trim();
  return " " + label + ": " + text + (/[.!?]$/.test(text) ? "" : ".");
}

function tradeLabel(rec) {
  return TRADE_COUNT_LABEL[rec.tradeCountMethod] || "trades";
}

function statsHtml(stats, rec) {
  const gap = stats.benchReturnPct == null || stats.returnPct == null ? null : round1(stats.returnPct - stats.benchReturnPct);
  return `<p class="bt-window">${esc(stats.window)}</p>
    ${stats.note ? `<p class="bt-flag">${esc(stats.note)}</p>` : ""}
    <dl class="facts bt-facts">
      <div><dt>Return</dt><dd class="${toneClass(stats.returnPct)}">${btPct(stats.returnPct)}</dd></div>
      <div><dt>Max drawdown</dt><dd class="${toneClass(stats.maxDdPct)}">${btPct(stats.maxDdPct)}</dd></div>
      <div><dt>Trades</dt><dd>${stats.trades == null ? "—" : Number(stats.trades).toLocaleString("en-US")}<small>${esc(tradeLabel(rec))}</small></dd></div>
      <div><dt>Benchmark</dt><dd class="${toneClass(stats.benchReturnPct)}">${btPct(stats.benchReturnPct)}</dd></div>
      <div><dt>Vs benchmark</dt><dd class="${toneClass(gap)}">${btPoints(gap)}</dd></div>
    </dl>`;
}

function viewForYear(rec, doc, yearKey) {
  const year = rec.years && rec.years[yearKey];
  if (!year) return { empty: "No backtest data for this year." };
  const native = (rec.equity && rec.equity.points) || [];
  const strat = rebaseSlice(native, year.startDate, year.endDate, year.startEquity);
  const bench = benchSeriesFor(rec, doc, year.startDate, year.endDate, false);
  const note = year.complete ? "" : (yearKey === "2026"
    ? "2026 is year-to-date through the last backtest bar."
    : "Partial year. This test does not cover the full calendar year.");
  return {
    strat,
    bench: bench.points,
    benchName: bench.name,
    summary: yearKey + " backtest return " + btPct(year.returnPct) + ", max drawdown " + btPct(year.maxDdPct) + ".",
    html: statsHtml({
      window: yearKey + " · " + isoLong(year.startDate) + " – " + isoLong(year.endDate),
      note,
      returnPct: year.returnPct,
      maxDdPct: year.maxDdPct,
      trades: year.trades,
      benchReturnPct: year.benchReturnPct
    }, rec)
  };
}

function viewForAll(rec, doc) {
  const equity = rec.equityFrom2020;
  if (!equity || !equity.points || !equity.points.length) return { empty: "No backtest data for this year." };
  const shared = uses2019Anchor(equity);
  const strat = equity.points.map(([date, value]) => ({ date, equity: value }));
  const bench = benchSeriesFor(rec, doc, equity.startDate, equity.endDate, shared);
  const start = equity.start || 10000;
  const end = equity.points[equity.points.length - 1][1];
  const returnPct = round1((end / start - 1) * 100);
  const drawdown = maxDrawdownPct([start, ...equity.points.map((point) => point[1])]);
  const maxDdPct = drawdown == null ? null : round1(drawdown);
  const trades = BACKTEST_YEARS.reduce((sum, year) => sum + ((rec.years[year] && rec.years[year].trades) || 0), 0);
  let benchReturnPct = null;
  if (bench.points.length) {
    const base = shared ? 10000 : bench.points[0].equity;
    benchReturnPct = round1((bench.points[bench.points.length - 1].equity / base - 1) * 100);
  }
  let note = "Rebased to $10,000 at the close before this window, or at the first bar if the test starts later.";
  if (String(equity.endDate).startsWith("2026")) note += " 2026 is year-to-date through the last backtest bar.";
  if (equity.startDate > "2020-01-15") note += " No backtest before " + isoLong(equity.startDate) + ".";
  const early = equity.startDate <= "2020-01-15" ? "2020–2026" : "First available date through the last bar";
  return {
    strat,
    bench: bench.points,
    benchName: bench.name,
    returnPct,
    maxDdPct,
    benchReturnPct,
    startDate: equity.startDate,
    endDate: equity.endDate,
    summary: early + " backtest return " + btPct(returnPct) + ", max drawdown " + btPct(maxDdPct) + ".",
    html: statsHtml({
      window: early + " · " + isoLong(equity.startDate) + " – " + isoLong(equity.endDate),
      note,
      returnPct,
      maxDdPct,
      trades,
      benchReturnPct
    }, rec) + `<p class="meta">Trade count is the sum of the calendar-year counts inside this window.</p>`
  };
}

function mountBacktest(strategy) {
  const method = document.getElementById("backtest-method");
  const body = document.getElementById("backtest-body");
  if (!method || !body) return;
  loadBacktestDoc().then((doc) => {
    const rec = (doc.strategies || []).find((item) => item.n === strategy.n);
    if (!rec) {
      method.textContent = "No backtest record for this strategy.";
      return;
    }
    const cost = sentence("Costs", rec.costs);
    const fill = sentence("Fill", rec.fill);
    method.textContent = "Signal on the close, fill at the next close, unless this strategy says otherwise." + cost + fill + " 2026 is year-to-date through the last backtest bar.";
    if (rec.method) {
      method.insertAdjacentHTML("afterend", `<p class="bt-method-note">${esc(rec.method)}</p>`);
    }
    if (!rec.hasBacktest) {
      body.innerHTML = `<p class="bt-gap">${esc(rec.gapReason || "No backtest data for this strategy.")}</p>` + caveatsHtml(rec);
      return;
    }
    const years = rec.years || {};
    const hasAll = !!(rec.equityFrom2020 && rec.equityFrom2020.points && rec.equityFrom2020.points.length);
    let selected = "all";
    if (!hasAll) selected = [...BACKTEST_YEARS].reverse().find((year) => years[year]) || "all";
    const buttons = [`<button type="button" role="tab" id="bt-tab-all" data-year="all" aria-selected="false" aria-controls="bt-panel"${hasAll ? "" : " disabled"}>All</button>`]
      .concat(BACKTEST_YEARS.map((year) => {
        const disabled = years[year] ? "" : " disabled";
        const title = years[year] ? "" : " title=\"No backtest data for this year\"";
        return `<button type="button" role="tab" id="bt-tab-${year}" data-year="${year}" aria-selected="false" aria-controls="bt-panel"${disabled}${title}>${year}</button>`;
      })).join("");
    body.innerHTML = `<div class="year-tabs" role="tablist" aria-label="Backtest year">${buttons}</div><div id="bt-panel" role="tabpanel"></div>${caveatsHtml(rec)}`;
    const list = body.querySelector(".year-tabs");
    const paint = () => {
      list.querySelectorAll("button").forEach((button) => {
        const on = button.dataset.year === selected;
        button.setAttribute("aria-selected", on ? "true" : "false");
        button.tabIndex = on ? 0 : -1;
      });
      const panel = document.getElementById("bt-panel");
      const active = document.getElementById("bt-tab-" + selected);
      if (active) panel.setAttribute("aria-labelledby", active.id);
      const view = selected === "all" ? viewForAll(rec, doc) : viewForYear(rec, doc, selected);
      if (view.empty || !view.strat || !view.strat.length) {
        panel.innerHTML = `<p class="bt-gap">${esc(view.empty || "No backtest data for this year.")}</p>`;
        return;
      }
      panel.innerHTML = `${view.html}<div class="bt-plot"></div><div class="legend"></div>`;
      const legendRow = panel.querySelector(".legend");
      const stratColor = strategy.color || "#3cba62";
      const benchColor = (strategy.benchmark && strategy.benchmark.color) || "#3c7dff";
      legendRow.innerHTML = `<span><i class="swatch" style="border-top-color:${stratColor}"></i>Backtest equity</span>` +
        (view.bench && view.bench.length ? `<span><i class="swatch dash" style="border-top-color:${benchColor}"></i>${esc(view.benchName)}</span>` : "");
      drawBacktestChart(panel.querySelector(".bt-plot"), view.strat, view.bench || [], {
        stratColor,
        benchColor,
        label: strategy.name + ". " + view.summary + (view.benchName ? " Dashed line is " + view.benchName + ", also rebased to $10,000." : "")
      });
    };
    list.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || button.disabled) return;
      selected = button.dataset.year;
      paint();
    });
    list.addEventListener("keydown", (event) => {
      const order = ["ArrowRight", "ArrowLeft", "Home", "End"];
      if (!order.includes(event.key)) return;
      const tabs = [...list.querySelectorAll("button:not(:disabled)")];
      const index = Math.max(0, tabs.findIndex((button) => button.dataset.year === selected));
      let next = index;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") next = 0;
      else next = tabs.length - 1;
      event.preventDefault();
      selected = tabs[next].dataset.year;
      tabs[next].focus();
      paint();
    });
    paint();
  }).catch((error) => {
    method.textContent = error && error.message ? error.message : "Backtest data could not be loaded.";
  });
}

function svgEl(name, attrs) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, String(value)));
  return el;
}

function axisMoney(value) {
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1000000) {
    const millions = abs / 1000000;
    return sign + "$" + (millions >= 10 ? millions.toFixed(1) : millions.toFixed(2)) + "M";
  }
  return sign + "$" + Math.round(abs).toLocaleString("en-US");
}

function niceStep(span, count) {
  if (!(span > 0) || !Number.isFinite(span)) return 1;
  const rough = span / Math.max(1, count);
  const pow = Math.pow(10, Math.floor(Math.log10(rough)));
  const scaled = rough / pow;
  const mult = scaled >= 7 ? 10 : scaled >= 3 ? 5 : scaled >= 1.5 ? 2 : 1;
  return mult * pow;
}

function axisTicks(min, max) {
  const step = niceStep(max - min, 4);
  if (!Number.isFinite(step) || step <= 0) return [min, max];
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let i = 0; i < 8; i++) {
    const value = start + i * step;
    if (value > max + step * 0.001) break;
    if (value >= min - step * 0.001) ticks.push(value);
  }
  return ticks.length ? ticks : [min, max];
}

function dateTicks(dates) {
  if (!dates.length) return [];
  if (dates.length === 1) return [{ date: dates[0], label: shortDate(dates[0]), anchor: "middle" }];
  const span = (Date.parse(dates[dates.length - 1] + "T00:00:00Z") - Date.parse(dates[0] + "T00:00:00Z")) / 86400000;
  if (span > 400) {
    const ticks = [];
    const seen = new Set();
    dates.forEach((date) => {
      const year = date.slice(0, 4);
      if (seen.has(year)) return;
      seen.add(year);
      ticks.push({ date, label: year, anchor: "middle" });
    });
    if (ticks.length) ticks[0].anchor = "start";
    if (ticks.length > 1) ticks[ticks.length - 1].anchor = "end";
    return ticks;
  }
  const count = Math.min(4, dates.length);
  const ticks = [];
  for (let k = 0; k < count; k++) {
    const index = Math.round(k * (dates.length - 1) / (count - 1));
    ticks.push({
      date: dates[index],
      label: shortDate(dates[index]),
      anchor: k === 0 ? "start" : k === count - 1 ? "end" : "middle"
    });
  }
  return ticks;
}

function drawBacktestChart(host, strat, bench, options) {
  host.replaceChildren();
  const width = 720;
  const height = 380;
  const pad = { l: 108, r: 16, t: 18, b: 36 };
  const series = strat.filter((point) => Number.isFinite(point.equity));
  const benchSeries = (bench || []).filter((point) => Number.isFinite(point.equity));
  const values = series.concat(benchSeries).map((point) => point.equity);
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  if (!Number.isFinite(dataMin) || !Number.isFinite(dataMax)) return;
  const span = Math.max(dataMax - dataMin, Math.abs(dataMax) * 0.04, 1);
  let min = dataMin - span * 0.08;
  let max = dataMax + span * 0.1;
  if (dataMin > 0) min = Math.max(min, Math.min(dataMin * 0.92, dataMin - span * 0.02));
  const dates = series.map((point) => point.date);
  const t0 = Date.parse((benchSeries.length && benchSeries[0].date < dates[0] ? benchSeries[0].date : dates[0]) + "T00:00:00Z");
  const lastDate = dates[dates.length - 1];
  const benchLast = benchSeries.length ? benchSeries[benchSeries.length - 1].date : lastDate;
  const t1 = Date.parse((benchLast > lastDate ? benchLast : lastDate) + "T00:00:00Z");
  const xOf = (date) => {
    const t = Date.parse(date + "T00:00:00Z");
    if (!(t1 > t0)) return pad.l + (width - pad.l - pad.r) / 2;
    return pad.l + ((t - t0) / (t1 - t0)) * (width - pad.l - pad.r);
  };
  const yOf = (value) => pad.t + (1 - (value - min) / (max - min)) * (height - pad.t - pad.b);
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": options.label });
  const ticks = axisTicks(min, max);
  ticks.forEach((tick) => {
    const y = yOf(tick);
    const capital = Math.abs(tick - 10000) < (max - min) * 0.015;
    svg.append(svgEl("line", {
      x1: pad.l, x2: width - pad.r, y1: y, y2: y,
      class: capital ? "grid-zero" : "grid-line",
      "stroke-width": capital ? "1.5" : "1"
    }));
    const text = svgEl("text", { x: 8, y: y + 5, "font-size": "15" });
    text.textContent = axisMoney(tick);
    svg.append(text);
  });
  if (min < 10000 && max > 10000 && !ticks.some((tick) => Math.abs(tick - 10000) < (max - min) * 0.015)) {
    const y = yOf(10000);
    svg.append(svgEl("line", {
      x1: pad.l, x2: width - pad.r, y1: y, y2: y,
      class: "grid-zero", "stroke-width": "1.5"
    }));
  }
  dateTicks(dates).forEach((tick) => {
    const text = svgEl("text", {
      x: xOf(tick.date),
      y: height - 12,
      "text-anchor": tick.anchor,
      "font-size": "15"
    });
    text.textContent = tick.label;
    svg.append(text);
  });
  const line = (points, color, dash) => {
    if (points.length < 2) return;
    const poly = svgEl("polyline", {
      fill: "none",
      stroke: color,
      "stroke-width": dash ? "2.25" : "3",
      "stroke-linejoin": "round",
      "stroke-linecap": "round",
      points: points.map((point) => xOf(point.date) + "," + yOf(point.equity)).join(" ")
    });
    if (dash) poly.setAttribute("stroke-dasharray", dash);
    svg.append(poly);
  };
  line(benchSeries, options.benchColor, "2 6");
  line(series, options.stratColor, "");
  const endDot = (points, color) => {
    if (!points.length) return;
    const point = points[points.length - 1];
    svg.append(svgEl("circle", { cx: xOf(point.date), cy: yOf(point.equity), r: "4.5", fill: color }));
  };
  endDot(benchSeries, options.benchColor);
  endDot(series, options.stratColor);
  const guide = svgEl("line", { y1: pad.t, y2: height - pad.b, class: "grid-line", "stroke-width": "1", visibility: "hidden" });
  svg.append(guide);
  host.append(svg);
  const readout = document.createElement("p");
  readout.className = "bt-readout";
  readout.hidden = true;
  host.append(readout);
  const xs = series.map((point) => xOf(point.date));
  const show = (clientX) => {
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return;
    const x = ((clientX - rect.left) / rect.width) * width;
    let best = 0;
    let bestDist = Infinity;
    xs.forEach((px, index) => {
      const dist = Math.abs(px - x);
      if (dist < bestDist) {
        bestDist = dist;
        best = index;
      }
    });
    const point = series[best];
    let benchText = "";
    if (benchSeries.length) {
      let chosen = benchSeries[0];
      benchSeries.forEach((item) => { if (item.date <= point.date) chosen = item; });
      benchText = " · buy-and-hold " + money(chosen.equity);
    }
    readout.hidden = false;
    readout.textContent = isoLong(point.date) + " · backtest " + money(point.equity) + benchText;
    guide.setAttribute("visibility", "visible");
    guide.setAttribute("x1", xs[best]);
    guide.setAttribute("x2", xs[best]);
  };
  svg.addEventListener("pointerdown", (event) => show(event.clientX));
  svg.addEventListener("pointermove", (event) => show(event.clientX));
  svg.addEventListener("pointerleave", () => {
    readout.hidden = true;
    guide.setAttribute("visibility", "hidden");
  });
}

/* ---------- Market mood gauge, positions heat map, live coin ticker (display only) ---------- */
const MOOD_ORDER = ["shock", "trend_down", "risk_off", "range", "trend_up"];
const MOOD_COLOR = {
  shock: "#c43be0",
  trend_down: "#e24632",
  risk_off: "#e8913a",
  range: "#f0c53a",
  trend_up: "#3cba62"
};
const MOOD_BLURB = {
  trend_up: "Prices are rising and sit above their long averages.",
  trend_down: "Prices are falling and sit under their long averages.",
  range: "Sideways. No clear trend either way.",
  risk_off: "Under the 50-day average. For stocks, bonds and gold are leading. For crypto, stocks are weak too.",
  shock: "A sharp drop from the recent high, and volatility has jumped."
};
function moodCaption(key, market) {
  if (key === "risk_off" && market === "crypto") return "Under the 50-day average while stocks are weak.";
  if (key === "risk_off") return "Under the 50-day average, with bonds and gold leading stocks.";
  return MOOD_BLURB[key] || "No plain-language label for this regime.";
}
function moodArc(cx, cy, r, a0, a1) {
  const x0 = cx + r * Math.cos(a0);
  const y0 = cy - r * Math.sin(a0);
  const x1 = cx + r * Math.cos(a1);
  const y1 = cy - r * Math.sin(a1);
  return "M " + x0.toFixed(2) + " " + y0.toFixed(2) + " A " + r + " " + r + " 0 0 0 " + x1.toFixed(2) + " " + y1.toFixed(2);
}
function moodDial(key, marketLabel) {
  const cx = 150;
  const cy = 118;
  const r = 96;
  const span = Math.PI / MOOD_ORDER.length;
  const gap = 0.045;
  const known = MOOD_ORDER.indexOf(key);
  const arcs = MOOD_ORDER.map((name, i) => {
    const a0 = Math.PI - i * span - gap;
    const a1 = Math.PI - (i + 1) * span + gap;
    const on = name === key;
    return `<path d="${moodArc(cx, cy, r, a0, a1)}" fill="none" stroke="${MOOD_COLOR[name]}" stroke-width="${on ? 18 : 12}" stroke-linecap="butt" opacity="${on ? "1" : "0.38"}"/>`;
  }).join("");
  let needle = "";
  if (known >= 0) {
    const ang = Math.PI - (known + 0.5) * span;
    const x2 = cx + 74 * Math.cos(ang);
    const y2 = cy - 74 * Math.sin(ang);
    const x1 = cx + 16 * Math.cos(ang);
    const y1 = cy - 16 * Math.sin(ang);
    needle = `<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}" stroke="#f3e2c4" stroke-width="3" stroke-linecap="round"/>`;
  }
  const title = marketLabel + ": " + regimeName(key);
  return `<svg viewBox="0 0 300 142" role="img" aria-label="${esc(title)}">${arcs}${needle}<circle cx="${cx}" cy="${cy}" r="7" fill="#1c6d78" stroke="#f3e2c4" stroke-width="2"/></svg>`;
}
function moodStrip(last20) {
  const counts = last20 || {};
  const parts = MOOD_ORDER.filter((key) => counts[key] > 0).map((key) => ({ key, n: counts[key] }));
  const total = parts.reduce((sum, part) => sum + part.n, 0);
  if (!total) return `<p class="mood-strip-note">No last-20 regime counts in this build.</p>`;
  const segs = parts.map((part) => {
    const short = { shock: "Shock", trend_down: "Down", risk_off: "Off", range: "Range", trend_up: "Up" };
    const label = (part.n >= 5 ? regimeName(part.key) : short[part.key]) + " " + part.n;
    return `<span class="mood-seg" style="flex:${part.n};background:${MOOD_COLOR[part.key]}" title="${esc(regimeName(part.key))}: ${part.n} of ${total}"><span>${esc(label)}</span></span>`;
  }).join("");
  const legend = parts.map((part) => regimeName(part.key) + " " + part.n).join(" · ");
  return `<div class="mood-strip" role="img" aria-label="Last ${total} closes by count, not in date order: ${esc(legend)}">${segs}</div>
    <p class="mood-strip-note">${esc(legend)}. Counts of the last ${total} closes, not the order of those days.</p>`;
}
function loggedRegimeDays() {
  const rows = [];
  (SIFT.updates || []).forEach((entry) => {
    if (!entry || entry.kind === "milestone") return;
    const line = (entry.items || []).find((item) => /Market regime:/i.test(item));
    if (!line) return;
    const match = line.match(/stocks \(SPY\) ([a-z][a-z ]*), crypto \(BTC\) ([a-z][a-z ]*)/i);
    if (!match) return;
    rows.push({
      date: entry.date,
      stock: match[1].trim().replace(/\s+/g, "_"),
      crypto: match[2].trim().replace(/\s+/g, "_")
    });
  });
  rows.sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
  const seen = new Set(rows.map((row) => row.date));
  const stock = SIFT.regime && SIFT.regime.stock;
  const crypto = SIFT.regime && SIFT.regime.crypto;
  const today = (stock && stock.date) || (crypto && crypto.date);
  if (today && !seen.has(today) && stock && crypto) {
    rows.push({ date: today, stock: stock.regime, crypto: crypto.regime });
  }
  return rows;
}
function moodDayCells(rows, market) {
  if (!rows.length) return `<p class="mood-strip-note">No day-by-day regime lines in the updates log yet.</p>`;
  return `<div class="mood-days">${rows.map((row) => {
    const key = row[market];
    const color = MOOD_COLOR[key] || "#b7a48a";
    return `<span class="mood-day" title="${esc(shortDate(row.date) + " · " + regimeName(key))}"><i style="background:${color}"></i>${esc(shortDate(row.date))}</span>`;
  }).join("")}</div>`;
}
function renderMoodCompact(stock, crypto) {
  const host = document.getElementById("mood-compact");
  if (!host) return;
  if (!stock && !crypto) {
    host.innerHTML = `<p class="desk-label">Market mood</p><p class="meta">No regime in this build.</p>`;
    return;
  }
  const bit = (block, label) => {
    if (!block) return "";
    const close = Number.isFinite(block.close) ? block.close.toLocaleString("en-US") : "—";
    return `<a class="mood-pill reg-${esc(block.regime)}" href="#mood-detail"><span>${esc(label)}</span><strong class="reg-word reg-${esc(block.regime)}">${esc(regimeName(block.regime))}</strong><em>${esc(block.asset || label)} ${esc(close)} · ${esc(block.date ? shortDate(block.date) : "—")}</em></a>`;
  };
  host.innerHTML = `<p class="desk-label">Market mood</p><div class="mood-pills">${bit(stock, "Stocks")}${bit(crypto, "Crypto")}</div>`;
}
function renderMood() {
  const host = document.getElementById("mood-mount");
  if (!host) return;
  const stock = SIFT.regime && SIFT.regime.stock;
  const crypto = SIFT.regime && SIFT.regime.crypto;
  if (!stock && !crypto) {
    host.innerHTML = `<div class="section-head"><h2>Market mood</h2><p>No regime data in this build.</p></div>`;
    renderMoodCompact(null, null);
    return;
  }
  const card = (block, market, label) => {
    if (!block) return "";
    const key = block.regime;
    const close = Number.isFinite(block.close) ? block.close.toLocaleString("en-US") : "—";
    return `<article class="mood-card reg-${esc(key)}">
      <h3>${esc(label)}</h3>
      <div class="mood-dial">${moodDial(key, label)}</div>
      <p class="mood-name reg-word reg-${esc(key)}">${esc(regimeName(key))}</p>
      <p class="mood-caption">${esc(moodCaption(key, market))}</p>
      <p class="mood-meta">${esc(block.asset || label)} close ${esc(close)} on ${esc(block.date ? shortDate(block.date) : "—")}</p>
      <h4>Last 20 closes</h4>
      ${moodStrip(block.last20)}
    </article>`;
  };
  const active = new Set([stock && stock.regime, crypto && crypto.regime].filter(Boolean));
  const keyList = MOOD_ORDER.map((key) => {
    const marks = [];
    if (stock && stock.regime === key) marks.push("Stocks");
    if (crypto && crypto.regime === key) marks.push("Crypto");
    return `<li class="${active.has(key) ? "is-on" : ""} reg-${key}"><b class="reg-word reg-${key}">${esc(regimeName(key))}</b><span>${esc(MOOD_BLURB[key])}</span>${marks.length ? `<em>${esc(marks.join(" · "))}</em>` : ""}</li>`;
  }).join("");
  const days = loggedRegimeDays();
  renderMoodCompact(stock, crypto);
  host.innerHTML = `<div class="section-head"><h2>Market mood</h2><p>The dial is today’s regime, the same daily label as the market regime section. Left is shock, right is trend up. It describes the last close. It is not a forecast.</p></div>
    <div class="mood-grid">${card(stock, "stocks", "Stocks · SPY")}${card(crypto, "crypto", "Crypto · BTC")}</div>
    <ul class="mood-key">${keyList}</ul>
    <div class="mood-log">
      <h3>Regime by day</h3>
      <p class="mood-strip-note">Oldest first, from the updates log. This is the ordered history. The bars above are only how many of the last 20 closes fell in each regime.</p>
      <div class="mood-log-grid">
        <div><span>Stocks</span>${moodDayCells(days, "stock")}</div>
        <div><span>Crypto</span>${moodDayCells(days, "crypto")}</div>
      </div>
    </div>`;
}

function positionCells(strategy) {
  if (strategy.planned) return [{ kind: "idle", label: "Not started" }];
  const text = strategy.forward || "";
  const held = text.match(/holds ([A-Z0-9][A-Z0-9.-]*(?:\s*,\s*[A-Z0-9][A-Z0-9.-]*)*)\s+as of/);
  if (held) {
    return held[1].split(",").map((symbol) => symbol.trim()).filter(Boolean).map((symbol) => ({ kind: "symbol", symbol, label: symbol }));
  }
  const open = text.match(/(\d+)\s+positions open/);
  if (open && Number(open[1]) > 0) return [{ kind: "open", count: Number(open[1]), label: open[1] + " open" }];
  const queuedMatch = text.match(/First buys queued for the next close:\s*([^.]+)/);
  const queued = queuedMatch ? queuedMatch[1].split(",").map((symbol) => symbol.trim()).filter(Boolean) : [];
  const flat = /flat by the close/i.test(strategy.plain || "");
  if (/100%\s*cash|\bin cash\b|waiting in cash|No buy signal/i.test(text) || queued.length || flat || (open && Number(open[1]) === 0)) {
    return [{ kind: "cash", label: "Cash", queued, note: flat ? "Flat by the close" : "" }];
  }
  return [{ kind: "unknown", label: "Unlisted" }];
}
function heatBackground(pct) {
  if (pct == null || !Number.isFinite(pct) || toneOf(pct).tone === "flat") return "#2c261c";
  const mag = Math.max(0, Math.min(1, Math.abs(pct) / 8));
  const alpha = (0.32 + mag * 0.68).toFixed(3);
  return pct > 0 ? "rgba(60, 186, 98, " + alpha + ")" : "rgba(226, 70, 50, " + alpha + ")";
}
function positionDetail(strategy, cell) {
  const pct = strategy.fwdPct;
  const pctText = pct == null || !Number.isFinite(pct) ? "no paper return yet" : signedPct(pct);
  const mark = strategy.asOfLabel ? " · " + strategy.asOfLabel : "";
  if (cell.kind === "cash") {
    const extra = [];
    if (cell.note) extra.push(cell.note);
    if (cell.queued && cell.queued.length) extra.push("queued for the next close: " + cell.queued.join(", "));
    return strategy.name + " · Cash · " + pctText + mark + (extra.length ? " · " + extra.join(" · ") : "") + ". Nothing is held at this mark. The percent is the account, not an open position.";
  }
  if (cell.kind === "symbol") {
    return strategy.name + " · " + cell.symbol + " · " + pctText + mark + ". That percent is the whole account’s paper return. Each position’s own unrealized change is not in the published data.";
  }
  if (cell.kind === "open") {
    return strategy.name + " · " + cell.count + " positions open · " + pctText + mark + ". The published note does not name the symbols or each position’s percent.";
  }
  if (cell.kind === "idle") return strategy.name + " · Not started. No paper account yet.";
  return strategy.name + " · Holdings not listed · " + pctText + mark + ".";
}
function renderPositions() {
  const host = document.getElementById("positions-mount");
  if (!host) return;
  const rows = SIFT.strategies.map((strategy) => {
    const cells = positionCells(strategy);
    const pct = strategy.fwdPct;
    const tone = pct == null ? "wait" : toneOf(pct).tone;
    const buttons = cells.map((cell) => {
      const detail = positionDetail(strategy, cell);
      const cashLike = cell.kind === "cash" || cell.kind === "idle";
      const style = cashLike ? "" : ` style="background:${heatBackground(pct)}"`;
      const cls = "heat-cell" + (cell.kind === "cash" ? " is-cash" : cell.kind === "idle" ? " is-idle" : cell.kind === "unknown" ? " is-idle" : "");
      return `<button type="button" class="${cls}"${style} data-detail="${esc(detail)}" aria-label="${esc(detail)}">${esc(cell.label)}</button>`;
    }).join("");
    const figure = strategy.planned || pct == null ? "—" : signedPct(pct);
    return `<div class="heat-row">
      <a class="heat-who" href="strategy.html?n=${strategy.n}"><span class="num">${String(strategy.n).padStart(2, "0")}</span><span class="heat-name">${esc(strategy.name)}</span><b class="tone-${tone}">${figure}</b></a>
      <div class="heat-cells">${buttons}</div>
    </div>`;
  }).join("");
  host.innerHTML = `<div class="section-head"><h2>Positions</h2><p>Each cell is a holding from that strategy’s latest forward note. Cash means nothing is held right now (a buy queued for the next close has not filled). Color is the account’s paper return since its own start — full color is about ±8% — because the published data does not include each position’s own unrealized percent. “9 open” means the note gives a count and no ticker.</p></div>
    <div class="heat-scale" aria-hidden="true"><span>−8%</span><i></i><span>+8%</span><span class="heat-cash-key">Cash</span></div>
    <p class="heat-readout" id="heat-readout" role="status">Hover or tap a cell for the strategy, the symbol, and the account’s percent change.</p>
    <div class="heat-grid">${rows}</div>`;
  const readout = host.querySelector("#heat-readout");
  host.querySelectorAll(".heat-cell").forEach((btn) => {
    const show = () => {
      host.querySelectorAll(".heat-cell.is-on").forEach((el) => el.classList.remove("is-on"));
      btn.classList.add("is-on");
      if (readout) readout.textContent = btn.getAttribute("data-detail") || "";
    };
    btn.addEventListener("pointerenter", show);
    btn.addEventListener("focus", show);
    btn.addEventListener("click", show);
  });
}

const TICKER_COINS = [
  { id: "bitcoin", sym: "BTC" },
  { id: "ethereum", sym: "ETH" },
  { id: "ripple", sym: "XRP" },
  { id: "binancecoin", sym: "BNB" },
  { id: "solana", sym: "SOL" },
  { id: "dogecoin", sym: "DOGE" },
  { id: "cardano", sym: "ADA" },
  { id: "tron", sym: "TRX" },
  { id: "chainlink", sym: "LINK" },
  { id: "avalanche-2", sym: "AVAX" }
];
const TICKER_URL = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids="
  + TICKER_COINS.map((coin) => coin.id).join(",")
  + "&sparkline=true&price_change_percentage=24h";
let tickerStarted = false;
let tickerAt = 0;
let tickerRows = null;
function formatCoin(n) {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  const v = Number(n);
  if (v >= 1000) return "$" + v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (v >= 1) return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (v >= 0.01) return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 6 });
}
function downsample(values, count) {
  if (values.length <= count) return values;
  const out = [];
  for (let i = 0; i < count; i += 1) out.push(values[Math.round(i * (values.length - 1) / (count - 1))]);
  return out;
}
function sparkSvg(prices, tone) {
  const samples = downsample(prices.filter((n) => Number.isFinite(n)), 32);
  if (samples.length < 2) return null;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "spark tone-" + (tone || "flat"));
  svg.setAttribute("viewBox", "0 0 72 18");
  svg.setAttribute("width", "72");
  svg.setAttribute("height", "18");
  svg.setAttribute("aria-hidden", "true");
  const min = Math.min.apply(null, samples);
  const max = Math.max.apply(null, samples);
  const span = max - min || 1;
  const pts = samples.map((p, i) => {
    const x = (i / (samples.length - 1)) * 72;
    const y = 16 - ((p - min) / span) * 14;
    return x.toFixed(1) + "," + y.toFixed(1);
  }).join(" ");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", "currentColor");
  line.setAttribute("stroke-width", "1.5");
  line.setAttribute("stroke-linejoin", "round");
  line.setAttribute("stroke-linecap", "round");
  line.setAttribute("points", pts);
  svg.append(line);
  return svg;
}
function tickerTone(pct) {
  if (pct == null || !Number.isFinite(pct) || Math.abs(pct) < 0.05) return "flat";
  return pct > 0 ? "up" : "down";
}
function paintTicker(rows) {
  const host = document.getElementById("crypto-ticker");
  if (!host) return;
  tickerRows = rows;
  const symbols = {};
  TICKER_COINS.forEach((coin) => { symbols[coin.id] = coin.sym; });
  const ordered = rows.filter((row) => symbols[row.id]).slice().sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0));
  if (!ordered.length) {
    tickerFail();
    return;
  }
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  host.classList.toggle("is-reduced", reduced);
  host.classList.remove("is-fallback");
  host.dataset.live = "1";
  host.title = "Market prices from CoinGecko. 24-hour change and a 7-day sparkline. Not paper-account results.";
  host.textContent = "";
  const label = document.createElement("div");
  label.className = "ticker-label";
  const strong = document.createElement("b");
  strong.textContent = "Coins";
  const sub = document.createElement("span");
  sub.textContent = "24h · 7d";
  label.append(strong, sub);
  const windowEl = document.createElement("div");
  windowEl.className = "ticker-window";
  const track = document.createElement("div");
  track.className = "ticker-track" + (reduced ? "" : " is-animated");
  const makeGroup = (clone) => {
    const group = document.createElement("div");
    group.className = "ticker-group";
    if (clone) group.setAttribute("aria-hidden", "true");
    ordered.forEach((row) => {
      const pct = row.price_change_percentage_24h;
      const tone = tickerTone(pct);
      const item = document.createElement("span");
      item.className = "tick";
      const sym = document.createElement("b");
      sym.textContent = symbols[row.id];
      const px = document.createElement("span");
      px.className = "tick-px";
      px.textContent = formatCoin(row.current_price);
      const chg = document.createElement("span");
      chg.className = "tick-chg tone-" + tone;
      chg.textContent = pct == null || !Number.isFinite(pct) ? "—" : signedPct(pct);
      item.append(sym, px, chg);
      const series = row.sparkline_in_7d && row.sparkline_in_7d.price;
      const spark = series ? sparkSvg(series, tone) : null;
      if (spark) item.append(spark);
      item.title = (row.name || symbols[row.id]) + " · " + px.textContent + " · 24h " + chg.textContent + " · 7-day line";
      group.append(item);
    });
    return group;
  };
  track.append(makeGroup(false));
  if (!reduced) track.append(makeGroup(true));
  windowEl.append(track);
  host.append(label, windowEl);
}
function tickerFail() {
  const host = document.getElementById("crypto-ticker");
  if (!host) return;
  if (host.dataset.live === "1") {
    host.title = "The last price refresh failed. Showing the previous quotes.";
    return;
  }
  host.classList.add("is-fallback");
  host.textContent = "";
  const note = document.createElement("p");
  note.className = "ticker-fallback";
  note.textContent = "Crypto prices unavailable";
  host.append(note);
}
async function loadTicker() {
  const now = Date.now();
  if (now - tickerAt < 50000) return;
  tickerAt = now;
  const ctrl = typeof AbortController === "function" ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), 12000) : null;
  try {
    const res = await fetch(TICKER_URL, { signal: ctrl ? ctrl.signal : undefined, headers: { accept: "application/json" } });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (!Array.isArray(data) || !data.length) throw new Error("empty");
    paintTicker(data);
  } catch (err) {
    tickerFail();
  } finally {
    if (timer) clearTimeout(timer);
  }
}
function renderTicker() {
  const host = document.getElementById("crypto-ticker");
  if (!host || tickerStarted) return;
  tickerStarted = true;
  loadTicker();
  setInterval(loadTicker, 60000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadTicker();
  });
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (motion.addEventListener) motion.addEventListener("change", () => { if (tickerRows) paintTicker(tickerRows); });
}
