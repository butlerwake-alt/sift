/* Homepage Paper Bots summary — same NEW_EXPERIMENTS feed as bots.html. Forward figures only. */
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
  function statusClass(status) {
    var s = String(status || "");
    if (s === "Data stale") return "status-stale";
    if (s === "In cash") return "status-cash";
    if (s === "No signal") return "status-nosignal";
    if (s === "Awaiting first mark") return "status-await";
    return "status-live";
  }

  function card(s) {
    var ddBadge = s.over_10pct_dd ? '<span class="dd-breach">Over 10% DD limit</span>' : "";
    var href = "bots.html?id=" + encodeURIComponent(s.id);
    return '<article class="paper-bot-home-card">' +
      '<div class="bot-card-top"><span class="exp-label">New experiment</span>' +
      '<span class="bot-status ' + statusClass(s.status) + '">' + esc(s.status || "—") + "</span></div>" +
      "<h3><a href=\"" + href + "\">" + esc(s.id) + " · " + esc(s.name) + "</a></h3>" +
      '<p class="bot-ret tone-' + tone(s.return) + '">' + money(s.equity) +
      " <small>(" + pct(s.return) + " forward)</small></p>" +
      '<dl class="bot-facts">' +
      "<div><dt>Exposure</dt><dd>" + (s.exposure == null ? "—" : (s.exposure * 100).toFixed(1) + "%") + "</dd></div>" +
      "<div><dt>Bench (matching period)</dt><dd>" + pct(s.benchmark_return) + "</dd></div>" +
      "<div><dt>Max drawdown</dt><dd>" + pct(s.max_drawdown) + " " + ddBadge + "</dd></div>" +
      "<div><dt>Last data update</dt><dd>" + esc(s.last_data_update || s.as_of || "—") + "</dd></div>" +
      "</dl>" +
      '<p class="meta"><a href="' + href + '">Rules, decision, fills →</a></p>' +
      "</article>";
  }

  function render() {
    var host = document.getElementById("paper-bots-mount");
    var stamp = document.getElementById("paper-bots-stamp");
    if (!host) return;
    var board = window.NEW_EXPERIMENTS;
    if (!board || !board.strategies) {
      host.innerHTML = "<p class=\"meta\">Paper bot data file is missing.</p>";
      return;
    }
    if (stamp) {
      stamp.textContent = "Forward paper only · " + (board.experiment_label || "New experiment") +
        " · last board build " + (board.generated_at || "");
    }
    host.innerHTML = board.strategies.map(card).join("");
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render);
  else render();
})();
