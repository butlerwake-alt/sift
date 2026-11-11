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
    line.setAttribute("stroke", tick === 10000 || tick === 5000 ? "#5c4634" : "#241e19");
    line.setAttribute("stroke-width", tick === 10000 || tick === 5000 ? "1.5" : "1");
    grid.append(line);
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", 8);
    text.setAttribute("y", tick === ticks[ticks.length - 1] ? y(tick) + 16 : y(tick) + 5);
    text.setAttribute("font-size", fontSize);
    text.textContent = money(tick);
    grid.append(text);
  });
  dates.forEach((key, index) => {
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", dates.length < 2 ? pad.l + (width - pad.l - pad.r) / 2 : pad.l + (index / (dates.length - 1)) * (width - pad.l - pad.r));
    text.setAttribute("y", height - 12);
    text.setAttribute("text-anchor", dates.length < 2 ? "middle" : index === 0 ? "start" : "end");
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

function renderBoard() {
  const board = document.getElementById("board");
  const tally = document.getElementById("tally");
  const counts = { up: 0, down: 0, flat: 0, wait: 0 };
  SIFT.strategies.forEach((strategy) => {
    const result = resultOf(strategy);
    counts[result.tone] += 1;
    const link = document.createElement("a");
    link.className = "card tone-" + result.tone;
    link.href = "strategy.html?n=" + strategy.n;
    link.target = "sift-" + strategy.n;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      window.open(link.href, link.target, "popup=yes,width=860,height=940,resizable=yes,scrollbars=yes");
    });
    const top = document.createElement("div");
    top.className = "card-top";
    top.innerHTML = `<span class="num">${String(strategy.n).padStart(2, "0")} · ${strategy.category}</span>${strategy.label ? labelChip(strategy) : `<span class="tag">${strategy.tag}</span>`}`;
    const title = document.createElement("h2");
    title.textContent = strategy.name;
    const plain = document.createElement("p");
    plain.className = "plain";
    plain.textContent = strategy.plain;
    const resultRow = document.createElement("div");
    resultRow.className = "result";
    resultRow.innerHTML = `<span class="figure">${result.figure}</span><span class="status">${result.word}</span>`;
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
    board.append(link);
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
  const book = document.getElementById("book");
  const ladder = document.getElementById("ladder");
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
    ladder.innerHTML = `<h2>Recorded change from the start</h2><ol>${rows}</ol>`;
  }
  const maxN = Math.max(...SIFT.strategies.map((item) => item.n));
  const open = (3 - (SIFT.strategies.length % 3)) % 3;
  for (let slot = maxN + 1; slot <= maxN + open; slot += 1) {
    const cell = document.createElement("article");
    cell.className = "slot";
    cell.innerHTML = `<div class="slot-top"><span class="num">${slot}</span><span class="tag">Open</span></div><h2>Room for a later test</h2><div class="empty-plot">Empty on purpose. A new strategy can take this card without moving the others.</div>`;
    board.append(cell);
  }
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
  return `<span class="chip ${proven ? "chip-proven" : "chip-hybrid"}">${proven ? "Proven in backtest" : "New forward-test hybrid"}</span>`;
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
  const host = document.getElementById("regime");
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
  host.innerHTML = `<h2>Current market regime</h2>
    <div class="regime-grid">${pill("stock", "Stocks · SPY", "stocks")}${pill("crypto", "Crypto · BTC", "crypto")}</div>
    <p class="regime-fit"><b>In their best regime today:</b> ${list(best)}</p>
    <p class="regime-fit"><b>Sitting out today:</b> ${list(sit)}</p>
    <p class="meta">A daily label from closing prices only, checked in this order: shock, trend down, risk-off, trend up, range. Updated ${SIFT.regime.asOf}. It describes the market; it is not a forecast.</p>`;
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
  return `<h2>Market regime fit</h2>
    <p>Best regime: ${r.best}. Sit out: ${r.sitOut}.${today ? ` Today (${today.asset}, ${shortDate(today.date)}): <b>${regimeName(today.regime)}</b>.` : ""}</p>
    <div class="rtable"><table><thead><tr><th>Regime</th><th>Backtest annualized return</th><th></th></tr></thead><tbody>${rowsHtml}</tbody></table></div>
    <p class="meta">Historical backtest by regime (new experiment, Nov 10, 2026). Separate from the forward paper result above.</p>`;
}

function whyHtml(strategy) {
  const why = strategy.why;
  if (!why || !why.text) return `<h2>Why we picked this</h2><p>No note recorded.</p>`;
  const flag = why.hasRecord ? "Original backtest on record" : "No original backtest record for these exact rules";
  return `<h2>Why we picked this</h2><div class="why-box"><p class="preview"><span>${flag}</span></p><p>${why.text}</p>${why.records && why.records.length ? `<p class="meta">Records: ${why.records.join(" · ")}</p>` : ""}</div>`;
}

function renderStrategy() {
  const params = new URLSearchParams(location.search);
  const strategy = SIFT.strategies.find((item) => item.n === Number(params.get("n")));
  const root = document.getElementById("detail");
  if (!strategy) {
    root.textContent = "That strategy is not on the board.";
    return;
  }
  document.title = strategy.name + " · SIFT";
  const result = resultOf(strategy);
  const plot = strategy.planned ? `<div class="empty-plot">Not launched. No marks to plot.</div>` : `<div class="plot" id="detail-plot"></div>`;
  root.innerHTML = `
    <p class="eyebrow">Strategy ${String(strategy.n).padStart(2, "0")} · ${strategy.category}</p>
    ${strategy.label ? `<p>${labelChip(strategy)}</p>` : ""}
    <h1>${strategy.name}</h1>
    <p class="lede">${strategy.plain}</p>
    <p class="result tone-${result.tone}"><span class="figure">${result.figure}</span><span class="status">${result.word}</span></p>
    ${factsHtml(result)}
    <p class="scale-note">${result.detail}. ${strategy.window} ${strategy.sleeveNote || "Each dot is one recorded daily mark from the paper-test records. Days without a mark are not drawn."}</p>
    ${plot}
    ${whyHtml(strategy)}
    <h2>What it is testing</h2>
    <p>${strategy.hypothesis}</p>
    <h2>Rules</h2>
    <ul class="rules">${strategy.rules.map((rule) => `<li>${rule}</li>`).join("")}</ul>
    ${regimeFitHtml(strategy)}
    <h2>${strategy.label ? "Backtest, historical (separate from the forward paper)" : "Backtest, in-sample"}</h2>
    <p>${strategy.backtest}</p>
    <h2>Forward paper</h2>
    <p>${strategy.forward}</p>
    <h2>Main risk</h2>
    <p>${strategy.risk}</p>
    ${strategy.label ? `<p class="fine">Backtest = new experiment dated Nov 10, 2026. Universe is today's list of large stocks/coins, so results carry survivorship bias. Halves are a stability check; parameters were not tuned. “Proven in backtest” means it passed the historical checks only; nothing is proven going forward. Forward paper only, not a forecast.</p>` : ""}
    <p class="fine">Paper only. Simulated $10,000. No live orders. Not financial advice. None of these strategies is proven. Source: ${SIFT.source}, ${SIFT.asOf}.</p>
  `;
  const host = document.getElementById("detail-plot");
  if (host) {
    drawChart(host, strategy);
    host.after(legend(strategy));
  }
}
