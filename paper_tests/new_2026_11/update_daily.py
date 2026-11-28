#!/usr/bin/env python3
"""Daily update entry for Nov 2026 new paper experiments.

Runs (or refreshes) each strategy's forward mark and rebuilds board.json +
new_experiments_data.js for the site. Does not touch existing desk paper engines,
template.json, data.js inputs, or memescan/data.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from common import EXPERIMENT_LABEL, FORWARD_START, TODAY, write_json  # noqa: E402
from strategies_crypto import run_b_new_1, run_b_new_2, run_b_new_3  # noqa: E402
from strategies_stock import run_s_new_1, run_s_new_2, run_s_new_3  # noqa: E402

NY = ZoneInfo("America/New_York")


def _days_running(as_of: str | None) -> int:
    try:
        mark = datetime.fromisoformat(str(as_of)).date() if as_of else TODAY
    except ValueError:
        mark = TODAY
    return max(0, (mark - FORWARD_START).days)


def _forward_summary(folder: Path) -> dict:
    state = json.loads((folder / "forward" / "state.json").read_text())
    eq_path = folder / "forward" / "equity.csv"
    rows = eq_path.read_text().strip().splitlines()
    latest = {}
    if len(rows) >= 2:
        headers = rows[0].split(",")
        latest = dict(zip(headers, rows[-1].split(",")))
    trades = []
    tp = folder / "forward" / "trades.csv"
    if tp.exists():
        lines = tp.read_text().strip().splitlines()
        trades = lines[1:] if len(lines) > 1 else []
    meta = json.loads((folder / "META.json").read_text())
    stats = json.loads((folder / "backtest_stats.json").read_text())
    equity = float(latest.get("equity") or 10000)
    start_eq = 10000.0
    ret = equity / start_eq - 1
    # max dd from forward equity
    vals = []
    for line in rows[1:]:
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                vals.append(float(parts[1]))
            except ValueError:
                pass
    peak = start_eq
    max_dd = 0.0
    for v in vals:
        peak = max(peak, v)
        max_dd = min(max_dd, v / peak - 1 if peak else 0)
    bench = None
    for k, v in latest.items():
        if k.startswith("benchmark"):
            try:
                bench = float(v)
            except ValueError:
                pass
    bench_ret = (bench / start_eq - 1) if bench else None
    return {
        "id": meta["id"],
        "name": meta["name"],
        "category": meta["category"],
        "experiment_label": EXPERIMENT_LABEL,
        "source": meta["source"],
        "why": meta["why"],
        "why_fail": meta["why_fail"],
        "rules": meta["rules"],
        "forward_start": FORWARD_START.isoformat(),
        "as_of": latest.get("date") or state.get("as_of"),
        "days_running": _days_running(latest.get("date") or state.get("as_of")),
        "equity": round(equity, 2),
        "return": ret,
        "benchmark_equity": bench,
        "benchmark_return": bench_ret,
        "beat_benchmark": (ret > bench_ret) if bench_ret is not None else None,
        "max_drawdown": max_dd,
        "over_10pct_dd": max_dd < -0.10,
        "forward_trades": len(trades),
        "idle_cash_income": (
            float(latest["idle_cash_income"])
            if latest.get("idle_cash_income") not in (None, "")
            else state.get("idle_cash_income")
            if state.get("idle_cash_income") is not None
            else state.get("funding_cash")
            if state.get("funding_cash") is not None
            else 0.0
        ),
        "idle_cash_label": (
            "Funding income (cash-and-carry)"
            if meta["id"] == "B-NEW-2"
            else "Idle cash (BIL)"
            if meta["category"] == "Stock Strategy"
            else "Idle cash (USD, no T-bill on this rule)"
        ),
        "backtest": {
            "cagr": stats.get("cagr"),
            "sharpe": stats.get("sharpe"),
            "deflated_sharpe": stats.get("deflated_sharpe"),
            "max_drawdown": stats.get("max_drawdown"),
            "trades": stats.get("trades"),
            "win_rate": stats.get("win_rate"),
            "average_trade": stats.get("average_trade"),
            "time_in_market": stats.get("time_in_market"),
            "over_10pct_dd": stats.get("over_10pct_dd"),
            "crash_periods": stats.get("crash_periods"),
            "label": stats.get("label"),
            "start": stats.get("start"),
            "end": stats.get("end"),
            "extra": {k: stats[k] for k in stats if k.startswith("benchmark") or k.startswith("comparison") or k in ("funding_income", "worst_dip")},
        },
        "equity_curve": [
            {"date": line.split(",")[0], "equity": float(line.split(",")[1])}
            for line in rows[1:]
            if len(line.split(",")) >= 2
        ],
        "state": state,
    }


def main() -> int:
    print(f"New experiments update {TODAY.isoformat()} — {EXPERIMENT_LABEL}")
    runners = [
        ("S-NEW-1", run_s_new_1),
        ("S-NEW-2", run_s_new_2),
        ("S-NEW-3", run_s_new_3),
        ("B-NEW-1", run_b_new_1),
        ("B-NEW-2", run_b_new_2),
        ("B-NEW-3", run_b_new_3),
    ]
    results = []
    for sid, fn in runners:
        print(f"  running {sid}…")
        out = fn()
        print(f"    forward equity={out['forward'].get('equity')} backtest CAGR={out['stats'].get('cagr')}")
        results.append(_forward_summary(HERE / sid))

    desk_bot = {
        "id": "DESK-BOT-EXISTING",
        "name": "Desk Paper Bot (existing)",
        "category": "Crypto Bot",
        "experiment_label": "Existing desk paper bot (read-only; not a new experiment)",
        "note": "Provisional quantdesk b1/b2 vol-target bots are excluded from rankings. This card is read-only; engine files under /workspace/quantdesk are not modified here. If tearsheets are absent on this host, status is unavailable.",
        "available": False,
        "excluded_from_rankings": True,
        "reason_excluded": "b1/b2 vol-targeted variants are left out of all rankings by standing desk rule.",
    }
    # Attempt read-only discovery without writing
    for path in (
        Path("/workspace/quantdesk/reports/2026-11-05/b_voltarget_trend"),
        ROOT / "quantdesk" / "reports" / "2026-11-05" / "b_voltarget_trend",
    ):
        if path.exists():
            desk_bot["available"] = True
            desk_bot["source_path"] = str(path)
            break

    board = {
        "generated_at": datetime.now(NY).isoformat(),
        "experiment_label": EXPERIMENT_LABEL,
        "forward_start": FORWARD_START.isoformat(),
        "cost_note": "New tests use 1.5× the desk's usual fee/slippage. Idle cash earns BIL where the rules allow.",
        "dd_limit": 0.10,
        "ranking_note": "Vol-targeted trend b1/b2 variants are excluded from all rankings.",
        "strategies": results,
        "desk_bot_existing": desk_bot,
    }
    write_json(HERE / "board.json", board)
    js = (
        "/* Generated by paper_tests/new_2026_11/update_daily.py — new experiments only. */\n"
        "window.NEW_EXPERIMENTS = " + json.dumps(board, indent=1) + ";\n"
    )
    (ROOT / "new_experiments_data.js").write_text(js)
    print(f"Wrote board.json and new_experiments_data.js ({len(results)} strategies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
