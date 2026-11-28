/* Bot Paper Testing page — presentation only; numbers from new_experiments_data.js */
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
  function spark(curve) {
    var values = (curve || []).map(function (p) { return p.equity; }).filter(isFinite);
    if (values.length < 2) return '<span class="spark-empty">—</span>';
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

  function botCard(s) {
    var ret = s.return;
    var benchGap = s.benchmark_return == null || ret == null ? null : ret - s.benchmark_return;
    var ddBadge = s.over_10pct_dd ? '<span class="dd-breach">Over 10% DD limit</span>' : "";
    return '<article class="bot-card">' +
      '<div class="bot-card-top"><span class="chip chip-bot">Crypto Bot</span><span class="exp-label">' + esc(s.experiment_label) + "</span></div>" +
      "<h2>" + esc(s.id) + " · " + esc(s.name) + "</h2>" +
      '<p class="bot-ret tone-' + tone(ret) + '">' + money(s.equity) + " <small>(" + pct(ret) + ")</small></p>" +
      spark(s.equity_curve) +
      '<dl class="bot-facts">' +
      "<div><dt>Vs benchmark</dt><dd class=\"tone-" + tone(benchGap) + "\">" + (benchGap == null ? "—" : pct(benchGap)) + "</dd></div>" +
      "<div><dt>Max drawdown</dt><dd>" + pct(s.max_drawdown) + " " + ddBadge + "</dd></div>" +
      "<div><dt>Forward trades</dt><dd>" + (s.forward_trades == null ? "—" : s.forward_trades) + "</dd></div>" +
      "<div><dt>Days running</dt><dd>" + (s.days_running == null ? "—" : s.days_running) + "</dd></div>" +
      "<div><dt>" + esc(s.idle_cash_label || "Idle cash") + "</dt><dd>" + money(s.idle_cash_income) + "</dd></div>" +
      "</dl>" +
      '<p class="meta"><a href="' + esc(s.source) + '" rel="noopener">Source</a></p>' +
      '<details class="lb-help"><summary>Why we picked this</summary><p>' + esc(s.why) + "</p></details>" +
      '<details class="lb-help"><summary>Why this could fail</summary><p>' + esc(s.why_fail) + "</p></details>" +
      '<details class="lb-help"><summary>Historical backtest (not forward)</summary><p>CAGR ' + pct(s.backtest && s.backtest.cagr) +
      " · Sharpe " + (s.backtest && s.backtest.sharpe != null ? Number(s.backtest.sharpe).toFixed(2) : "—") +
      " · Max DD " + pct(s.backtest && s.backtest.max_drawdown) +
      " · Trades " + ((s.backtest && s.backtest.trades) != null ? s.backtest.trades : "—") +
      ". Label: Historical backtest, not forward results.</p></details>" +
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
    var bots = (board.strategies || []).filter(function (s) { return s.category === "Crypto Bot"; });
    mount.innerHTML = bots.map(botCard).join("") + (board.desk_bot_existing ? deskCard(board.desk_bot_existing) : "");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render);
  else render();
})();
