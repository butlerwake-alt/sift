/* New Stock Strategies (2026-11) gallery + optional ?new= detail. Presentation only. */
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
  function spark(curve) {
    var values = (curve || []).map(function (p) { return p.equity; }).filter(isFinite);
    if (values.length < 2) return '<span class="spark-empty">Day-1 mark</span>';
    var min = Math.min.apply(null, values), max = Math.max.apply(null, values), span = max - min || 1;
    var w = 160, h = 36;
    var pts = values.map(function (v, i) {
      var x = (i / (values.length - 1)) * w;
      var y = (h - 3) - ((v - min) / span) * (h - 6);
      return x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    var t = tone(values[values.length - 1] / values[0] - 1);
    return '<svg class="path-spark tone-' + t + '" viewBox="0 0 ' + w + " " + h + '" width="' + w + '" height="' + h + '" aria-hidden="true"><polyline fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round" points="' + pts + '"/></svg>';
  }

  function card(s) {
    var ddBadge = s.over_10pct_dd ? '<span class="dd-breach">Over 10% DD limit</span>' : "";
    var bt = s.backtest || {};
    return '<article class="new-stock-card" id="' + esc(s.id) + '">' +
      '<div class="card-top"><span class="chip chip-stock">Stock Strategy</span><span class="exp-label">' + esc(s.experiment_label) + "</span></div>" +
      "<h2><a href=\"strategy.html?new=" + encodeURIComponent(s.id) + "\">" + esc(s.id) + " · " + esc(s.name) + "</a></h2>" +
      '<p class="bot-ret tone-' + tone(s.return) + '">' + money(s.equity) + " <small>(" + pct(s.return) + ")</small></p>" +
      spark(s.equity_curve) +
      '<dl class="bot-facts">' +
      "<div><dt>Vs benchmark</dt><dd class=\"tone-" + tone((s.return || 0) - (s.benchmark_return || 0)) + "\">" + pct(s.benchmark_return) + "</dd></div>" +
      "<div><dt>Max drawdown</dt><dd>" + pct(s.max_drawdown) + " " + ddBadge + "</dd></div>" +
      "<div><dt>Forward trades</dt><dd>" + (s.forward_trades == null ? "—" : s.forward_trades) + "</dd></div>" +
      "<div><dt>Days running</dt><dd>" + (s.days_running == null ? "—" : s.days_running) + "</dd></div>" +
      "<div><dt>" + esc(s.idle_cash_label || "Idle cash (BIL)") + "</dt><dd>" + money(s.idle_cash_income) + "</dd></div>" +
      "</dl>" +
      '<p class="meta"><a href="' + esc(s.source) + '" rel="noopener">Source</a></p>' +
      '<details class="lb-help"><summary>Why we picked this</summary><p>' + esc(s.why) + "</p></details>" +
      '<details class="lb-help"><summary>Why this could fail</summary><p>' + esc(s.why_fail) + "</p></details>" +
      '<details class="lb-help"><summary>Historical backtest (not forward)</summary><p>Label: Historical backtest, not forward results. CAGR ' +
      pct(bt.cagr) + " · Sharpe " + (bt.sharpe != null ? Number(bt.sharpe).toFixed(2) : "—") +
      " · Deflated Sharpe " + (bt.deflated_sharpe != null ? Number(bt.deflated_sharpe).toFixed(2) : "—") +
      " · Max DD " + pct(bt.max_drawdown) + " · Trades " + (bt.trades != null ? bt.trades : "—") +
      " · Win rate " + pct(bt.win_rate) + " · Avg trade " + money(bt.average_trade) +
      " · Time in market " + pct(bt.time_in_market) + ".</p></details>" +
      "</article>";
  }

  function detail(s) {
    var bt = s.backtest || {};
    var crash = bt.crash_periods || {};
    var rules = (s.rules || []).map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("");
    var ddBadge = s.over_10pct_dd ? '<span class="dd-breach">Over 10% DD limit</span>' : "";
    return '<article class="strategy-detail new-stock-detail">' +
      '<p class="desk-label">' + esc(s.experiment_label) + "</p>" +
      '<p><span class="chip chip-stock">Stock Strategy</span> <span class="chip">' + esc(s.id) + "</span></p>" +
      "<h1>" + esc(s.name) + "</h1>" +
      '<p class="bot-ret tone-' + tone(s.return) + '">' + money(s.equity) + " <small>(" + pct(s.return) + ")</small> " + ddBadge + "</p>" +
      spark(s.equity_curve) +
      "<h2>Rules (frozen)</h2><ul>" + rules + "</ul>" +
      "<h2>Why we picked this</h2><p>" + esc(s.why) + "</p>" +
      "<h2>Why this could fail</h2><p>" + esc(s.why_fail) + "</p>" +
      '<p class="meta"><a href="' + esc(s.source) + '" rel="noopener">Source</a></p>' +
      "<h2>Historical backtest, not forward results</h2>" +
      "<p>CAGR " + pct(bt.cagr) + " · Sharpe " + (bt.sharpe != null ? Number(bt.sharpe).toFixed(2) : "—") +
      " · Deflated Sharpe " + (bt.deflated_sharpe != null ? Number(bt.deflated_sharpe).toFixed(2) : "—") +
      " · Max DD " + pct(bt.max_drawdown) + (bt.over_10pct_dd ? ' <span class="dd-breach">Over 10% DD limit</span>' : "") +
      " · Trades " + (bt.trades != null ? bt.trades : "—") +
      " · Win rate " + pct(bt.win_rate) +
      " · Avg trade " + money(bt.average_trade) +
      " · Time in market " + pct(bt.time_in_market) +
      " · Window " + esc(bt.start) + " → " + esc(bt.end) + ".</p>" +
      "<p>2020 crash: return " + pct(crash["2020"] && crash["2020"].return) + ", max DD " + pct(crash["2020"] && crash["2020"].max_drawdown) +
      ". 2022 crash: return " + pct(crash["2022"] && crash["2022"].return) + ", max DD " + pct(crash["2022"] && crash["2022"].max_drawdown) + ".</p>" +
      '<p class="meta"><a href="strategy.html#new-stock-strategies">← All new stock strategies</a> · <a href="scoreboard.html">Scoreboard</a></p>' +
      "</article>";
  }

  function render() {
    var board = window.NEW_EXPERIMENTS;
    var mount = document.getElementById("new-stock-mount");
    var section = document.getElementById("new-stock-strategies");
    var deskDetail = document.getElementById("detail");
    var id = param("new");
    var deskN = param("n");

    if (!board) {
      if (mount) mount.innerHTML = "<p>New experiment data file is missing.</p>";
      return;
    }
    var stocks = (board.strategies || []).filter(function (s) { return s.category === "Stock Strategy"; });

    if (id) {
      var found = stocks.filter(function (s) { return s.id === id; })[0];
      if (deskDetail) {
        deskDetail.innerHTML = found ? detail(found) : "<p>Unknown new stock strategy id.</p>";
      }
      if (section) section.hidden = true;
      return;
    }

    if (deskN && section) {
      // Existing desk strategy detail — keep gallery below as secondary
      section.classList.add("is-secondary");
    }

    if (mount) {
      mount.innerHTML = stocks.map(card).join("") || "<p>No new stock strategies.</p>";
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render);
  else render();
})();
