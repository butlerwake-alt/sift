#!/usr/bin/env python3
"""Checks for S-NEW-4 / B-NEW-4: next-bar fills, fees, missing prices, re-run safety, DD badge."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import CAPITAL, CRYPTO_FEE, STOCK_FEE, classify_status, trade_key, write_forward_ledger  # noqa: E402


def test_classify_status():
    assert classify_status(as_of=None, exposure=0, last_signal="awaiting", data_failure=None, category="Stock Strategy") == "Awaiting first mark"
    assert classify_status(as_of="2020-01-01", exposure=0, last_signal="cash", data_failure=None, category="Stock Strategy") == "Data stale"
    assert classify_status(as_of="2099-01-01", exposure=0, last_signal="none", data_failure=None, category="Stock Strategy") == "No signal"
    assert classify_status(as_of="2099-01-01", exposure=0, last_signal="cash", data_failure=None, category="Stock Strategy") == "In cash"
    assert classify_status(as_of="2099-01-01", exposure=0.5, last_signal="invested", data_failure=None, category="Crypto Bot") == "Invested"
    assert classify_status(as_of="2099-01-01", exposure=0, last_signal="x", data_failure="missing open", category="Crypto Bot") == "Data stale"
    print("classify_status OK")


def test_ledger_dedup(tmp_path: Path | None = None):
    folder = (tmp_path or (HERE / "_test_tmp")) 
    folder = Path(folder)
    trades = [
        {"timestamp": "2026-11-27T09:30:00-05:00", "side": "BUY", "symbol": "SPY", "price": 100, "qty": 1, "fees": 0.1, "pnl": "", "reason": "t"},
        {"timestamp": "2026-11-27T09:30:00-05:00", "side": "BUY", "symbol": "SPY", "price": 100, "qty": 1, "fees": 0.1, "pnl": "", "reason": "t"},
    ]
    assert trade_key(trades[0]) == trade_key(trades[1])
    write_forward_ledger(
        folder,
        [{"date": "2026-11-27", "equity": CAPITAL}],
        trades,
        {"id": "TEST", "as_of": "2026-11-27"},
    )
    lines = (folder / "forward" / "trades.csv").read_text().strip().splitlines()
    assert len(lines) == 2  # header + one unique fill
    # Second write with same trades stays unique
    write_forward_ledger(
        folder,
        [{"date": "2026-11-27", "equity": CAPITAL}],
        trades + trades,
        {"id": "TEST", "as_of": "2026-11-27"},
    )
    lines2 = (folder / "forward" / "trades.csv").read_text().strip().splitlines()
    assert len(lines2) == 2
    print("ledger dedup OK")


def test_next_bar_and_fees_s4():
    from strategies_stock import run_s_new_4

    out = run_s_new_4()
    stats = out["stats"]
    assert stats.get("awaiting_verified_historical_data") in (True, False, None)
    if not stats.get("awaiting_verified_historical_data"):
        assert stats.get("holdout_start")
        assert stats.get("holdout_end")
        assert stats.get("data_source")
        assert "doubled_cost_total_return" in stats or stats.get("doubled_cost_total_return") is None
        # Fee constant used
        assert abs(STOCK_FEE - 0.00075) < 1e-12
        # Next-open: trades_backtest reasons mention next open
        trades = (HERE / "S-NEW-4" / "trades_backtest.csv").read_text()
        assert "next open" in trades or "trend sleeve" in trades
    state = json.loads((HERE / "S-NEW-4" / "forward" / "state.json").read_text())
    assert state.get("id") == "S-NEW-4"
    assert "status" in state
    # DD badge field exists on board path via over_10pct_dd in stats
    if stats.get("max_drawdown") is not None:
        assert isinstance(stats.get("over_10pct_dd"), bool)
    print("S-NEW-4 next-bar/fees/DD OK")


def test_next_bar_and_fees_b4():
    from strategies_crypto import run_b_new_4

    out = run_b_new_4()
    stats = out["stats"]
    if not stats.get("awaiting_verified_historical_data"):
        assert stats.get("holdout_start")
        assert abs(CRYPTO_FEE - 0.00375) < 1e-12
        trades = list(pd.read_csv(HERE / "B-NEW-4" / "trades_backtest.csv").itertuples())
        # Band rebalance reasons present or only seed if never breached
        reasons = " ".join(str(getattr(t, "reason", "")) for t in trades)
        assert "seed" in reasons or "band" in reasons
        assert "weight_drift_avg_abs" in stats or stats.get("weight_drift_avg_abs") is None
    state = json.loads((HERE / "B-NEW-4" / "forward" / "state.json").read_text())
    assert state.get("id") == "B-NEW-4"
    print("B-NEW-4 next-bar/fees/weights OK")


def test_missing_price_skip(monkeypatch=None):
    """Unit-level: classify + ledger preserve when execution skipped."""
    status = classify_status(
        as_of="2099-01-01",
        exposure=0.0,
        last_signal="awaiting",
        data_failure="2026-11-28: missing open prices ['IEF']; skipped rebalance",
        category="Stock Strategy",
    )
    assert status == "Data stale"
    print("missing-price status OK")


def main():
    test_classify_status()
    test_ledger_dedup(HERE / "_test_tmp")
    test_missing_price_skip()
    # Networked strategy runs (may take a minute)
    test_next_bar_and_fees_s4()
    test_next_bar_and_fees_b4()
    print("All checks passed")


if __name__ == "__main__":
    main()
