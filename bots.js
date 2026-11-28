/* Paper Bots — list + detail from new_experiments_data.js (presentation only). */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function pct(v) {
    if (v == null || !isFinite(v)) return "—";
    var sign = v > 0.00005 ? "+" : v < -0.00005 ? "−" : "";
    return sign + (Math.abs(v) * 100).toFixed(2) + "%";
  }
  function money(v) {
    if (v == null || !isFinite(v)) return "—";
    return "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function tone(v) {
    if (v == null || !isFinite(v)) return "flat";
    if (v > 0.0005) return "up";
    if (v < -0.0005) return "down";
    return "flat";
  }
  function param(name) {
    try { return new URLSearchParams(location.search).get(name); } catch (e) { return null; }
  }
  function statusClass(status) {
    var s = String(status || "");
    if (s === "Data stale") return "status-stale";
    if (s === "In cash") return "status-cash";
    if (s === "No signal") return "status-nosignal";
    if (s === "Awaiting first mark") return "status-await";
    return "status-live";
  }
  function spark(curve) {
    var values = (curve || []).map(function (p) { return p.equity; }).filter(isFinite);
    if (values.length < 2) return '<span class="spark-empty">Awaiting marks</span>';
    var min = Math.min.apply(null, values), max = Math.max.apply(null, values), span = max - min || 1;
    var w = 220, h = 48;
    var pts = values.map(function (v, i) {
      var x = (i / (values.length - 1)) * w;
      var y = (h - 3) - ((v - min) / span) * (h - 6);
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    var t = tone(values[values.length - 1] / values[0] - 1);
    return '<svg class="path-spark tone-' + t + '" viewBox="0 0 ' + w + " " + h + '" width="' + w + '" height="' + h + '" aria-hidden="true"><polyline fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round" points="' + pts + '"/></svg>';
  }
  function fillTable(fills) {
    if (!fills || !fills.length) return '<p class="meta">No simulated fills yet.</p>';
    var body = fills.slice().reverse().map(function (f) {
      return "<tr><td>" + esc(f.timestamp || f.date || "") + "</td><td>" + esc(f.side) + "</td><td>" + esc(f.symbol) +
        "</td><td class=\"num-col\">" + esc(f.price) + "</td><td class=\"num-col\">" + esc(f.qty || f.shares || "") +
        "</td><td class=\"num-col\">" + esc(f.fees) + "</td><td>" + esc(f.reason) + "</td></tr>";
    }).join("");
    return '<div class="rtable lb-scroll"><table><thead><tr><th>When</th><th>Side</th><th>Symbol</th><th>Price</th><th>Qty</th><th>Fees</th><th>Reason</th></tr></thead><tbody>' +
      body + "</tbody></table></div>";
  }
  function decisionBlock(s) {
    var d = s.latest_decision;
    if (!d) return '<p class="meta">No decision recorded yet.</p>';
    return "<pre class=\"decision-json\">" + esc(JSON.stringify(d, null, 2)) + "</pre>";
  }
  function histBlock(s) {
    var bt = s.backtest || {};
    if (bt.awaiting_verified_historical_data) {
      return '<p class="await-hist"><strong>Awaiting verified historical data.</strong> ' +
        esc(bt.awaiting_reason || "Insufficient history for a trustworthy backtest.") +
        " Historical stats are left empty. This does not imply the bot is profitable.</p>";
    }
    var extra = bt.extra || {};
    return       "<p>Label: Historical backtest, not forward results. Holdout " +
      esc(bt.holdout_start || bt.start) + " → " + esc(bt.holdout_end || bt.end) +
      ". Source: " + esc(bt.data_source || "see META") + ".</p>" +
      "<p>" + (bt.cagr != null ? "CAGR " + pct(bt.cagr) : "CAGR —") +
      " · Max DD " + pct(bt.max_drawdown) +
      (bt.over_10pct_dd ? ' <span class="dd-breach">Over 10% DD limit</span>' : "") +
      " · Turnover " + (bt.turnover != null ? Number(bt.turnover).toFixed(2) : "—") +
      " · Fills " + (bt.fill_count != null ? bt.fill_count : (bt.trades != null ? bt.trades : "—")) +
      " · Benchmark gap " + pct(bt.benchmark_gap) +
      " · Doubled-cost return " + pct(bt.doubled_cost_total_return) +
      " · Doubled-cost max DD " + pct(bt.doubled_cost_max_drawdown) + ".</p>" +
      (bt.vs_published_research ? "<p class=\"meta\">" + esc(bt.vs_published_research) + "</p>" : "");
  }

  function botCard(s) {
    var ret = s.return;
    var benchGap = s.benchmark_return == null || ret == null ? null : ret - s.benchmark_return;
    var ddBadge = s.over_10pct_dd ? '<span class="dd-breach">Over 10% DD limit</span>' : "";
    var chip = s.category === "Stock Strategy" ? "chip-stock" : "chip-bot";
    return '<article class="bot-card" id="' + esc(s.id) + '">' +
      '<div class="bot-card-top"><span class="chip ' + chip + '">' + esc(s.category) + '</span><span class="exp-label">' + esc(s.experiment_label) + "</span></div>" +
      "<h2><a href=\"bots.html?id=" + encodeURIComponent(s.id) + "\">" + esc(s.id) + " · " + esc(s.name) + "</a></h2>" +
      '<p class="bot-status ' + statusClass(s.status) + '">' + esc(s.status || "—") + "</p>" +
      '<p class="bot-ret tone-' + tone(ret) + '">' + money(s.equity) + " <small>(" + pct(ret) + " forward)</small></p>" +
      spark(s.equity_curve) +
      '<dl class="bot-facts">' +
      "<div><dt>Exposure</dt><dd>" + (s.exposure == null ? "—" : (s.exposure * 100).toFixed(1) + "%") + "</dd></div>" +
      "<div><dt>Forward vs bench</dt><dd class=\"tone-" + tone(benchGap) + "\">" + (benchGap == null ? "—" : pct(benchGap)) + "</dd></div>" +
      "<div><dt>Bench return</dt><dd>" + pct(s.benchmark_return) + "</dd></div>" +
      "<div><dt>Max drawdown</dt><dd>" + pct(s.max_drawdown) + " " + ddBadge + "</dd></div>" +
      "<div><dt>Last data update</dt><dd>" + esc(s.last_data_update || s.as_of || "—") + "</dd></div>" +
      "<div><dt>Forward fills</dt><dd>" + (s.forward_trades == null ? "—" : s.forward_trades) + "</dd></div>" +
      "</dl>" +
      '<p class="meta"><a href="bots.html?id=' + encodeURIComponent(s.id) + '">Open detail →</a></p>' +
      "</article>";
  }

  function detail(s) {
    var ret = s.return;
    var ddBadge = s.over_10pct_dd ? '<span class="dd-breach">Over 10% DD limit</span>' : "";
    var chip = s.category === "Stock Strategy" ? "chip-stock" : "chip-bot";
    var rules = (s.rules || []).map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("");
    return '<article class="bot-detail">' +
      '<p><a class="back" href="bots.html">← All paper bots</a></p>' +
      '<div class="bot-card-top"><span class="chip ' + chip + '">' + esc(s.category) + '</span><span class="exp-label">' + esc(s.experiment_label) + "</span></div>" +
      "<h1>" + esc(s.id) + " · " + esc(s.name) + "</h1>" +
      '<p class="bot-status ' + statusClass(s.status) + '">' + esc(s.status || "—") + "</p>" +
      '<p class="bot-ret tone-' + tone(ret) + '">' + money(s.equity) + " <small>(" + pct(ret) + " forward paper)</small> " + ddBadge + "</p>" +
      spark(s.equity_curve) +
      '<dl class="bot-facts">' +
      "<div><dt>Exposure</dt><dd>" + (s.exposure == null ? "—" : (s.exposure * 100).toFixed(1) + "%") + "</dd></div>" +
      "<div><dt>Benchmark return</dt><dd>" + pct(s.benchmark_return) + "</dd></div>" +
      "<div><dt>Max drawdown</dt><dd>" + pct(s.max_drawdown) + "</dd></div>" +
      "<div><dt>Last data update</dt><dd>" + esc(s.last_data_update || s.as_of || "—") + "</dd></div>" +
      "<div><dt>Days running</dt><dd>" + (s.days_running == null ? "—" : s.days_running) + "</dd></div>" +
      "<div><dt>" + esc(s.idle_cash_label || "Idle cash") + "</dt><dd>" + money(s.idle_cash_income) + "</dd></div>" +
      "</dl>" +
      (s.data_failure ? '<p class="data-fail" role="status">Data issue: ' + esc(s.data_failure) + "</p>" : "") +
      "<h2>Exact rules (frozen)</h2><ul>" + rules + "</ul>" +
      '<p class="meta"><a href="' + esc(s.source) + '" rel="noopener">Source</a></p>' +
      "<h2>Why we picked this</h2><p>" + esc(s.why) + "</p>" +
      "<h2>Why this could fail</h2><p>" + esc(s.why_fail) + "</p>" +
      "<h2>Latest decision</h2>" + decisionBlock(s) +
      "<h2>Simulated fill log</h2>" + fillTable(s.fills) +
      "<h2>Historical backtest (not forward)</h2>" + histBlock(s) +
      "</article>";
  }

  function deskCard(desk) {
    return '<article class="bot-card bot-card-existing">' +
      '<div class="bot-card-top"><span class="chip chip-existing">Desk Paper Bot (existing)</span></div>' +
      "<h2>" + esc(desk.name) + "</h2>" +
      "<p class=\"meta\">" + esc(desk.experiment_label) + "</p>" +
      "<p>" + esc(desk.note) + "</p>" +
      "<p class=\"meta\">Available on this host: " + (desk.available ? "yes" : "no") + ". Excluded from rankings: yes (" + esc(desk.reason_excluded) + ").</p>" +
      "</article>";
  }

  function render() {
    var board = window.NEW_EXPERIMENTS;
    var mount = document.getElementById("bots-mount");
    var stamp = document.getElementById("bots-stamp");
    if (!board || !mount) {
      if (mount) mount.innerHTML = "<p>New experiment data file is missing.</p>";
      return;
    }
    if (stamp) stamp.textContent = board.experiment_label + " · generated " + (board.generated_at || "");
    var id = param("id") || (location.hash ? location.hash.replace(/^#/, "") : "");
    var all = board.strategies || [];
    if (id) {
      var found = all.filter(function (s) { return s.id === id; })[0];
      mount.className = "bot-detail-mount";
      mount.innerHTML = found ? detail(found) : "<p>Unknown paper bot id.</p>";
      return;
    }
    mount.className = "bot-grid";
    mount.innerHTML = all.map(botCard).join("") + (board.desk_bot_existing ? deskCard(board.desk_bot_existing) : "");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render);
  else render();
})();
