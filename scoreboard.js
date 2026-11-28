/* 1-Year Strategy Scoreboard — presentation only. */
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
    if (v == null || !isFinite(v)) return "";
    if (v > 0.0005) return "tone-up";
    if (v < -0.0005) return "tone-down";
    return "tone-flat";
  }
  function dayCount(start, end) {
    if (!start || !end) return null;
    var a = Date.parse(start), b = Date.parse(end);
    if (!isFinite(a) || !isFinite(b)) return null;
    return Math.max(0, Math.round((b - a) / 86400000));
  }
  function maxDd(points, capital) {
    var vals = (points || []).map(function (p) { return p.equity; }).filter(isFinite);
    if (!vals.length && capital) vals = [capital];
    if (vals.length < 1) return null;
    var peak = vals[0], worst = 0;
    vals.forEach(function (v) {
      peak = Math.max(peak, v);
      worst = Math.min(worst, v / peak - 1);
    });
    return worst;
  }
  function forwardSharpe(points) {
    var vals = (points || []).map(function (p) { return p.equity; }).filter(isFinite);
    if (vals.length < 6) return null;
    var rets = [];
    for (var i = 1; i < vals.length; i++) rets.push(vals[i] / vals[i - 1] - 1);
    var mean = rets.reduce(function (a, b) { return a + b; }, 0) / rets.length;
    var varr = rets.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / (rets.length - 1);
    var sd = Math.sqrt(varr);
    if (!sd) return null;
    return (mean / sd) * Math.sqrt(252);
  }

  function collectRows() {
    var rows = [];
    var capital = (window.SIFT && SIFT.capital) || 10000;

    (SIFT && SIFT.strategies || []).forEach(function (s) {
      if (s.planned) return;
      // Exclude vol-targeted desk b1/b2 naming if ever present
      var name = s.name || "";
      if (/\bb1\b|\bb2\b|vol-?target/i.test(name) && /desk bot/i.test(name)) return;
      var ret = s.fwdPct != null ? s.fwdPct / 100 : (s.latest != null ? s.latest / capital - 1 : null);
      var dd = maxDd(s.points, capital);
      var bench = null;
      if (s.benchmark && s.benchmark.points && s.benchmark.points.length) {
        var bp = s.benchmark.points;
        bench = bp[bp.length - 1].equity / capital - 1;
      }
      rows.push({
        name: s.name,
        id: "desk-" + s.n,
        category: "Existing Desk",
        start: s.start,
        days: dayCount(s.start, s.asOf),
        equity: s.latest,
        ret: ret,
        benchRet: bench,
        beat: ret != null && bench != null ? ret > bench : null,
        maxDd: dd,
        overDd: dd != null && dd < -0.10,
        sharpe: forwardSharpe(s.points),
        trades: null,
        href: "strategy.html?n=" + s.n
      });
    });

    var neo = window.NEW_EXPERIMENTS;
    (neo && neo.strategies || []).forEach(function (s) {
      rows.push({
        name: s.id + " · " + s.name,
        id: s.id,
        category: s.category,
        start: s.forward_start,
        days: s.days_running,
        equity: s.equity,
        ret: s.return,
        benchRet: s.benchmark_return,
        beat: s.beat_benchmark,
        maxDd: s.max_drawdown,
        overDd: !!s.over_10pct_dd,
        sharpe: forwardSharpe(s.equity_curve),
        trades: s.forward_trades,
        href: "bots.html?id=" + encodeURIComponent(s.id)
      });
    });

    // Memecoin audit aggregate (buyable graded) as one scoreboard row
    fetch("memescan/data/board.json?t=" + Date.now()).then(function (r) {
      if (!r.ok) throw new Error("no memescan");
      return r.json();
    }).then(function (board) {
      var graded = (board.graded || []).filter(function (g) {
        return (g.rule_version || "v2") === "v2" && g.verdict !== "TRAP" && typeof g.net_return === "number";
      });
      if (!graded.length) return;
      var stake = 100;
      var pnl = graded.reduce(function (s, g) { return s + stake * g.net_return; }, 0);
      var invested = stake * graded.length;
      var ret = invested ? pnl / invested : 0;
      var wins = graded.filter(function (g) { return g.net_return > 0; }).length;
      rows.push({
        name: "Memescan paper book (CLEAN/WARN/UNKNOWN)",
        id: "memescan-v2",
        category: "Memecoin Audit",
        start: "2026-11-25",
        days: dayCount("2026-11-25", board.generated_at),
        equity: invested + pnl,
        ret: ret,
        benchRet: null,
        beat: null,
        maxDd: null,
        overDd: false,
        sharpe: null,
        trades: graded.length,
        href: "memescan.html",
        extra: wins + " wins / " + (graded.length - wins) + " losses"
      });
      window.__SCORE_ROWS = rows;
      paint();
    }).catch(function () {
      window.__SCORE_ROWS = rows;
      paint();
    });

    window.__SCORE_ROWS = rows;
    return rows;
  }

  function paint() {
    var host = document.getElementById("scoreboard-mount");
    if (!host) return;
    var cat = document.getElementById("filter-cat").value;
    var ddOnly = document.getElementById("filter-dd").checked;
    var rows = (window.__SCORE_ROWS || []).slice();
    rows = rows.filter(function (r) {
      if (cat !== "all" && r.category !== cat) return false;
      if (ddOnly && r.overDd) return false;
      return true;
    });
    rows.sort(function (a, b) {
      var as = a.sharpe, bs = b.sharpe;
      if (as == null && bs == null) return (b.ret || -999) - (a.ret || -999);
      if (as == null) return 1;
      if (bs == null) return -1;
      return bs - as;
    });
    var body = rows.map(function (r, i) {
      return "<tr>" +
        "<td class=\"num-col\">" + (i + 1) + "</td>" +
        "<th scope=\"row\"><a href=\"" + esc(r.href) + "\">" + esc(r.name) + "</a>" +
        (r.overDd ? ' <span class="dd-breach">Over 10% DD limit</span>' : "") + "</th>" +
        "<td>" + esc(r.category) + "</td>" +
        "<td>" + esc(r.start || "—") + "</td>" +
        "<td class=\"num-col\">" + (r.days == null ? "—" : r.days) + "</td>" +
        "<td class=\"num-col\">" + money(r.equity) + "</td>" +
        "<td class=\"num-col " + tone(r.ret) + "\">" + pct(r.ret) + "</td>" +
        "<td class=\"num-col " + tone(r.benchRet) + "\">" + pct(r.benchRet) + "</td>" +
        "<td>" + (r.beat == null ? "—" : r.beat ? "Yes" : "No") + "</td>" +
        "<td class=\"num-col\">" + pct(r.maxDd) + "</td>" +
        "<td class=\"num-col\">" + (r.sharpe == null ? "—" : r.sharpe.toFixed(2)) + "</td>" +
        "<td class=\"num-col\">" + (r.trades == null ? "—" : r.trades) + "</td>" +
        "</tr>";
    }).join("");
    host.innerHTML = '<table><thead><tr>' +
      "<th>#</th><th>Name</th><th>Category</th><th>Start</th><th>Days</th><th>Value</th><th>Return</th><th>Benchmark</th><th>Beat?</th><th>Max DD</th><th>Sharpe</th><th>Trades</th>" +
      "</tr></thead><tbody>" + (body || '<tr><td colspan="12">No rows match the filters.</td></tr>') + "</tbody></table>";
  }

  function init() {
    collectRows();
    paint();
    document.getElementById("filter-cat").addEventListener("change", paint);
    document.getElementById("filter-dd").addEventListener("change", paint);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
