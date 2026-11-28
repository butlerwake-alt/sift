#!/usr/bin/env python3
"""Crypto bot new experiments B-NEW-1..3. Paper only."""
from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from common import (
    CAPITAL,
    CRYPTO_FEE,
    EXPERIMENT_LABEL,
    FORWARD_START,
    GRID_FEE,
    HERE,
    StrategyMeta,
    classify_status,
    fetch_coinbase_daily,
    fetch_deribit_funding,
    load_yahoo,
    max_drawdown,
    summarize_backtest,
    turnover_from_trades,
    write_csv,
    write_forward_ledger,
    write_json,
)


def _month_starts(idx: pd.DatetimeIndex) -> list:
    s = pd.Series(1, index=idx)
    # first available bar of each calendar month
    return list(s.groupby([idx.year, idx.month]).head(1).index)


def run_b_new_1() -> dict:
    meta = StrategyMeta(
        id="B-NEW-1",
        name="BTC/ETH Monthly Rotation Bot",
        category="Crypto Bot",
        source="https://myprofitfactor.com/en/crypto/btc-eth-momentum-rotation-strategy/",
        why="Simple relative-strength rotation between the two largest coins. Frozen 90-day lookback and monthly cadence; no search.",
        why_fail="Crypto momentum fails in prolonged dual drawdowns; monthly decisions miss fast flips; 1.5× crypto costs are large on rotations.",
        rules=[
            "On the 1st available daily bar of each month, compare BTC and ETH 90-day returns using closes already known.",
            "Hold the one with the higher positive return; if both <= 0, hold cash (USD).",
            "Fill at that day's open.",
            f"Cost: {CRYPTO_FEE*100:.3f}% per side (1.5× desk crypto 0.25%).",
            "Comparison only: 60-day and 120-day lookbacks.",
        ],
        benchmarks=["BTC buy-and-hold", "ETH buy-and-hold", "50/50 BTC/ETH"],
        fee_per_side=CRYPTO_FEE,
    )
    btc = fetch_coinbase_daily("BTC-USD", date(2016, 1, 1))
    eth = fetch_coinbase_daily("ETH-USD", date(2016, 1, 1))
    idx = btc.index.intersection(eth.index)
    btc = btc.loc[idx]
    eth = eth.loc[idx]
    bil = load_yahoo(["BIL"], "2016-01-01")["BIL"].reindex(idx).ffill()

    def simulate(lookback: int):
        cash = CAPITAL
        units = 0.0
        asset = None
        entry_basis = 0.0
        equity = []
        trades = []
        starts = _month_starts(idx)
        start_set = set(starts)
        for d in idx:
            # decision at month start using prior closes (already known before open)
            if d in start_set:
                loc = idx.get_loc(d)
                if isinstance(loc, int) and loc >= lookback:
                    btc_ret = float(btc["Close"].iloc[loc - 1] / btc["Close"].iloc[loc - 1 - lookback] - 1)
                    eth_ret = float(eth["Close"].iloc[loc - 1] / eth["Close"].iloc[loc - 1 - lookback] - 1)
                    choice = None
                    if btc_ret > 0 or eth_ret > 0:
                        choice = "BTC" if btc_ret >= eth_ret and btc_ret > 0 else ("ETH" if eth_ret > 0 else None)
                        if btc_ret > 0 and eth_ret > 0:
                            choice = "BTC" if btc_ret >= eth_ret else "ETH"
                    # exit existing
                    if asset and (choice != asset):
                        px = float((btc if asset == "BTC" else eth)["Open"].loc[d])
                        proceeds = units * px
                        fee = proceeds * CRYPTO_FEE
                        cash = proceeds - fee
                        pnl = cash - entry_basis
                        trades.append({"date": str(d.date()), "side": "SELL", "symbol": asset, "price": px, "qty": units, "fees": round(fee, 4), "pnl": round(pnl, 2), "reason": f"rotate lookback={lookback}"})
                        units = 0.0
                        asset = None
                    if choice and asset is None:
                        px = float((btc if choice == "BTC" else eth)["Open"].loc[d])
                        fee = cash * CRYPTO_FEE
                        spend = cash - fee
                        units = spend / px
                        entry_basis = cash
                        cash = 0.0
                        asset = choice
                        trades.append({"date": str(d.date()), "side": "BUY", "symbol": asset, "price": px, "qty": units, "fees": round(fee, 4), "pnl": None, "reason": f"month start lookback={lookback}"})
                    if choice is None and asset is not None:
                        px = float((btc if asset == "BTC" else eth)["Open"].loc[d])
                        proceeds = units * px
                        fee = proceeds * CRYPTO_FEE
                        cash = proceeds - fee
                        pnl = cash - entry_basis
                        trades.append({"date": str(d.date()), "side": "SELL", "symbol": asset, "price": px, "qty": units, "fees": round(fee, 4), "pnl": round(pnl, 2), "reason": "both <=0 → cash"})
                        units = 0.0
                        asset = None
            # mark
            if asset:
                px = float((btc if asset == "BTC" else eth)["Close"].loc[d])
                eq = units * px
            else:
                # idle cash: no T-bill for USD crypto cash in this rule (USD). Keep flat USD.
                eq = cash
            equity.append({"date": str(d.date()), "equity": round(eq if asset else cash, 2), "holding": asset or "CASH"})
        return equity, trades

    equity, trades = simulate(90)
    eq_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in equity})
    closed = [t for t in trades if t.get("pnl") is not None]
    stats = summarize_backtest(eq_s, closed, periods_per_year=365)
    held = sum(1 for r in equity if r["holding"] != "CASH")
    stats["time_in_market"] = held / len(equity) if equity else None
    btc_bh = CAPITAL * btc["Close"] / float(btc["Close"].iloc[0])
    eth_bh = CAPITAL * eth["Close"] / float(eth["Close"].iloc[0])
    mix = 0.5 * btc_bh + 0.5 * (CAPITAL * eth["Close"] / float(eth["Close"].iloc[0]))
    stats["benchmark_btc_total_return"] = float(btc_bh.iloc[-1] / CAPITAL - 1)
    stats["benchmark_eth_total_return"] = float(eth_bh.iloc[-1] / CAPITAL - 1)
    stats["benchmark_50_50_total_return"] = float(mix.iloc[-1] / CAPITAL - 1)
    for lb in (60, 120):
        e, t = simulate(lb)
        s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in e})
        stats[f"comparison_{lb}d"] = {
            "note": "comparison only, not a pick",
            "total_return": float(s.iloc[-1] / CAPITAL - 1),
            "max_drawdown": max_drawdown(s),
            "trades": sum(1 for x in t if x.get("pnl") is not None),
        }

    folder = HERE / "B-NEW-1"
    write_json(folder / "META.json", meta.to_public())
    write_json(folder / "backtest_stats.json", stats)
    write_csv(folder / "equity_backtest.csv", equity)
    write_csv(folder / "trades_backtest.csv", trades)

    # Forward
    fwd_idx = idx[idx.date >= FORWARD_START]
    cash = CAPITAL
    units = 0.0
    asset = None
    entry_basis = 0.0
    forward_trades = []
    forward_equity = []
    starts = set(_month_starts(idx))
    for d in fwd_idx:
        if d in starts:
            loc = idx.get_loc(d)
            if isinstance(loc, int) and loc >= 90:
                btc_ret = float(btc["Close"].iloc[loc - 1] / btc["Close"].iloc[loc - 1 - 90] - 1)
                eth_ret = float(eth["Close"].iloc[loc - 1] / eth["Close"].iloc[loc - 1 - 90] - 1)
                choice = None
                if btc_ret > 0 or eth_ret > 0:
                    if btc_ret > 0 and eth_ret > 0:
                        choice = "BTC" if btc_ret >= eth_ret else "ETH"
                    else:
                        choice = "BTC" if btc_ret > 0 else "ETH"
                if asset and choice != asset:
                    px = float((btc if asset == "BTC" else eth)["Open"].loc[d])
                    proceeds = units * px
                    fee = proceeds * CRYPTO_FEE
                    cash = proceeds - fee
                    forward_trades.append({"timestamp": d.isoformat() + "Z", "side": "SELL", "symbol": asset, "price": px, "qty": units, "fees": round(fee, 4), "pnl": round(cash - entry_basis, 2), "reason": "monthly rotate"})
                    units = 0.0
                    asset = None
                if choice and asset is None:
                    px = float((btc if choice == "BTC" else eth)["Open"].loc[d])
                    fee = cash * CRYPTO_FEE
                    spend = cash - fee
                    units = spend / px
                    entry_basis = cash
                    cash = 0.0
                    asset = choice
                    forward_trades.append({"timestamp": d.isoformat() + "Z", "side": "BUY", "symbol": asset, "price": px, "qty": units, "fees": round(fee, 4), "pnl": "", "reason": "monthly rotate"})
                if choice is None and asset is not None:
                    px = float((btc if asset == "BTC" else eth)["Open"].loc[d])
                    proceeds = units * px
                    fee = proceeds * CRYPTO_FEE
                    cash = proceeds - fee
                    forward_trades.append({"timestamp": d.isoformat() + "Z", "side": "SELL", "symbol": asset, "price": px, "qty": units, "fees": round(fee, 4), "pnl": round(cash - entry_basis, 2), "reason": "both <=0"})
                    units = 0.0
                    asset = None
        if asset:
            px = float((btc if asset == "BTC" else eth)["Close"].loc[d])
            eq = units * px
        else:
            eq = cash
        b0 = float(btc["Close"].loc[fwd_idx[0]])
        forward_equity.append({"date": str(d.date()), "equity": round(eq, 2), "benchmark_btc": round(CAPITAL * float(btc["Close"].loc[d]) / b0, 2)})
    if not forward_equity:
        forward_equity = [{"date": FORWARD_START.isoformat(), "equity": CAPITAL, "benchmark_btc": CAPITAL}]
    state = {"cash": round(cash, 2), "units": units, "asset": asset, "as_of": forward_equity[-1]["date"], "experiment_label": EXPERIMENT_LABEL, "id": meta.id}
    write_csv(folder / "forward" / "equity.csv", forward_equity)
    write_csv(folder / "forward" / "trades.csv", forward_trades, fieldnames=["timestamp", "side", "symbol", "price", "qty", "fees", "pnl", "reason"])
    write_json(folder / "forward" / "state.json", state)
    return {"meta": meta.to_public(), "stats": stats, "forward": forward_equity[-1], "state": state}


def run_b_new_2() -> dict:
    meta = StrategyMeta(
        id="B-NEW-2",
        name="Cash-and-Carry Bot (BTC, 1x hedged)",
        category="Crypto Bot",
        source="https://www.investwealth.com/learn/guides/crypto-basis-trade",
        why="Harvests perpetual funding while staying roughly delta-neutral at 1x. Frozen hedge band 90–110%; no leverage beyond the 1x short hedge.",
        why_fail="Funding can flip negative for long stretches; hedge slippage and fees; exchange/counterparty risk is not modeled.",
        rules=[
            "Hold BTC spot and short an equal dollar amount of BTC perpetual (1x, delta-neutral).",
            "Collect or pay every funding print from Deribit public history.",
            "Rebalance legs if notional drift leaves the 90–110% band.",
            f"Spot/perp trade cost: {CRYPTO_FEE*100:.3f}% per side (1.5× desk).",
            "Comparison only: ETH version.",
            "Note: exchange/counterparty risk is not modeled.",
            "Benchmark: T-bill (BIL) yield.",
        ],
        benchmarks=["T-bill (BIL)"],
        fee_per_side=CRYPTO_FEE,
    )
    spot = fetch_coinbase_daily("BTC-USD", date(2019, 6, 1))
    funding = fetch_deribit_funding("BTC", date(2019, 6, 1))
    bil = load_yahoo(["BIL"], "2019-06-01")["BIL"]

    # Align daily marks: apply sum of funding prints each day to short notional
    fund_daily = funding["funding"].resample("1D").sum().fillna(0.0)
    idx = spot.index.intersection(fund_daily.index)
    spot = spot.loc[idx]
    fund_daily = fund_daily.loc[idx]

    cash = CAPITAL  # used to buy spot; short is synthetic
    # Start: buy spot with half? Classic cash-and-carry: use capital for spot, short equal notional on perp (margin assumed covered by spot book in this paper model)
    # Model: deploy all capital into spot BTC; short equal USD notional; funding accrues to cash pocket; mark equity = spot_value + funding_pnl_cash - fees; short PnL offsets spot delta
    equity = []
    trades = []
    px0 = float(spot["Close"].iloc[0])
    fee0 = CAPITAL * CRYPTO_FEE
    spot_units = (CAPITAL - fee0) / px0
    short_notional = spot_units * px0  # USD
    short_entry_px = px0
    funding_cash = 0.0
    trades.append({"date": str(idx[0].date()), "side": "BUY_SPOT", "symbol": "BTC", "price": px0, "qty": spot_units, "fees": round(fee0, 4), "pnl": None, "reason": "open cash-and-carry"})
    trades.append({"date": str(idx[0].date()), "side": "SHORT_PERP", "symbol": "BTC-PERP", "price": px0, "qty": spot_units, "fees": round(fee0, 4), "pnl": None, "reason": "open 1x hedge"})
    # charge short open fee from funding pocket / capital
    funding_cash -= fee0

    worst_dip = 0.0
    peak = CAPITAL
    for d in idx[1:]:
        px = float(spot["Close"].loc[d])
        spot_val = spot_units * px
        short_pnl = short_notional * (short_entry_px - px) / short_entry_px  # approx linear
        # funding: short receives funding when rate > 0 (longs pay shorts) under typical crypto convention interest_8h
        f = float(fund_daily.loc[d])
        funding_cash += short_notional * f
        # rebalance if hedge ratio outside 0.9–1.1
        hedge_ratio = short_notional / spot_val if spot_val else 1.0
        if hedge_ratio < 0.9 or hedge_ratio > 1.1:
            # close short and reopen at current px for equal notional
            fee = short_notional * CRYPTO_FEE
            funding_cash -= fee
            trades.append({"date": str(d.date()), "side": "REBALANCE_SHORT", "symbol": "BTC-PERP", "price": px, "qty": spot_units, "fees": round(fee, 4), "pnl": None, "reason": f"hedge_ratio={hedge_ratio:.3f}"})
            short_notional = spot_val
            short_entry_px = px
            short_pnl = 0.0
        eq = spot_val + short_pnl + funding_cash
        peak = max(peak, eq)
        worst_dip = min(worst_dip, eq / peak - 1)
        equity.append({"date": str(d.date()), "equity": round(eq, 2), "funding_cash": round(funding_cash, 2), "spot_value": round(spot_val, 2), "short_pnl": round(short_pnl, 2)})

    eq_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in equity})
    stats = summarize_backtest(eq_s, [{"pnl": funding_cash}], periods_per_year=365)
    stats["trades"] = sum(1 for t in trades if t["side"] in ("REBALANCE_SHORT", "BUY_SPOT"))
    stats["win_rate"] = None
    stats["average_trade"] = None
    stats["time_in_market"] = 1.0
    stats["funding_income"] = round(funding_cash, 2)
    stats["worst_dip"] = worst_dip
    stats["fees_note"] = "Includes open and rebalance fees at 1.5× desk crypto rate"
    # BIL benchmark
    bil_a = bil.reindex(eq_s.index).ffill()
    if bil_a.notna().sum() > 2:
        stats["benchmark_tbill_total_return"] = float(bil_a.dropna().iloc[-1] / bil_a.dropna().iloc[0] - 1)

    # ETH comparison only (lightweight)
    try:
        eth_spot = fetch_coinbase_daily("ETH-USD", date(2019, 6, 1))
        eth_fund = fetch_deribit_funding("ETH", date(2019, 6, 1))
        eth_fd = eth_fund["funding"].resample("1D").sum().fillna(0.0)
        eidx = eth_spot.index.intersection(eth_fd.index)
        e_cash = -CAPITAL * CRYPTO_FEE
        e_units = (CAPITAL - CAPITAL * CRYPTO_FEE) / float(eth_spot["Close"].loc[eidx[0]])
        e_short_n = e_units * float(eth_spot["Close"].loc[eidx[0]])
        e_entry = float(eth_spot["Close"].loc[eidx[0]])
        e_rows = []
        for d in eidx[1:]:
            px = float(eth_spot["Close"].loc[d])
            spot_val = e_units * px
            short_pnl = e_short_n * (e_entry - px) / e_entry
            e_cash += e_short_n * float(eth_fd.loc[d])
            e_rows.append(spot_val + short_pnl + e_cash)
        stats["comparison_eth"] = {
            "note": "comparison only, not a pick",
            "total_return": float(e_rows[-1] / CAPITAL - 1) if e_rows else None,
            "max_drawdown": max_drawdown(pd.Series(e_rows)) if e_rows else None,
        }
    except Exception as err:
        stats["comparison_eth"] = {"note": "comparison only, not a pick", "error": str(err)}

    folder = HERE / "B-NEW-2"
    write_json(folder / "META.json", meta.to_public())
    write_json(folder / "backtest_stats.json", stats)
    write_csv(folder / "equity_backtest.csv", equity)
    write_csv(folder / "trades_backtest.csv", trades)

    # Forward from FORWARD_START
    fwd = idx[idx.date >= FORWARD_START]
    if len(fwd) == 0:
        fwd = idx[-1:]
    px0 = float(spot["Close"].loc[fwd[0]])
    fee0 = CAPITAL * CRYPTO_FEE
    spot_units = (CAPITAL - fee0) / px0
    short_notional = spot_units * px0
    short_entry_px = px0
    funding_cash = -fee0
    forward_trades = [
        {"timestamp": fwd[0].isoformat() + "Z", "side": "BUY_SPOT", "symbol": "BTC", "price": px0, "qty": spot_units, "fees": round(fee0, 4), "pnl": "", "reason": "open cash-and-carry"},
        {"timestamp": fwd[0].isoformat() + "Z", "side": "SHORT_PERP", "symbol": "BTC-PERP", "price": px0, "qty": spot_units, "fees": round(fee0, 4), "pnl": "", "reason": "open 1x hedge"},
    ]
    forward_equity = []
    for d in fwd:
        px = float(spot["Close"].loc[d])
        spot_val = spot_units * px
        short_pnl = short_notional * (short_entry_px - px) / short_entry_px
        if d != fwd[0]:
            funding_cash += short_notional * float(fund_daily.loc[d])
        hedge_ratio = short_notional / spot_val if spot_val else 1.0
        if hedge_ratio < 0.9 or hedge_ratio > 1.1:
            fee = short_notional * CRYPTO_FEE
            funding_cash -= fee
            forward_trades.append({"timestamp": d.isoformat() + "Z", "side": "REBALANCE_SHORT", "symbol": "BTC-PERP", "price": px, "qty": spot_units, "fees": round(fee, 4), "pnl": "", "reason": f"hedge_ratio={hedge_ratio:.3f}"})
            short_notional = spot_val
            short_entry_px = px
            short_pnl = 0.0
        eq = spot_val + short_pnl + funding_cash
        forward_equity.append({"date": str(d.date()), "equity": round(eq, 2), "benchmark_tbill": CAPITAL})
    state = {
        "spot_units": spot_units,
        "short_notional": short_notional,
        "short_entry_px": short_entry_px,
        "funding_cash": round(funding_cash, 2),
        "as_of": forward_equity[-1]["date"],
        "experiment_label": EXPERIMENT_LABEL,
        "id": meta.id,
        "counterparty_risk": "not modeled",
    }
    write_csv(folder / "forward" / "equity.csv", forward_equity)
    write_csv(folder / "forward" / "trades.csv", forward_trades, fieldnames=["timestamp", "side", "symbol", "price", "qty", "fees", "pnl", "reason"])
    write_json(folder / "forward" / "state.json", state)
    return {"meta": meta.to_public(), "stats": stats, "forward": forward_equity[-1], "state": state}


def run_b_new_3() -> dict:
    meta = StrategyMeta(
        id="B-NEW-3",
        name="Spot Grid Bot (BTC, frozen)",
        category="Crypto Bot",
        source="https://edgoro.com/blog/grid-trading-bot-bitcoin-backtest",
        why="Frozen geometric grid tests whether range-bound BTC months can harvest mean reversion without discretionary tweaks.",
        why_fail="Strong trends leave the band and idle; marking inventory to market can show large unrealized losses; grid profits alone are misleading.",
        rules=[
            "Each month, start a fresh $10,000 book.",
            "Geometric grid centered on the month's first open, ±10% band, 20 lines, same BTC size per line.",
            "Spot only.",
            f"Fee: {GRID_FEE*100:.2f}% per fill (1.5× the stated 0.1%).",
            "Mark inventory to market at the month's close (never count only closed-grid profit).",
            "If price leaves the band, hold until the next monthly reset.",
        ],
        benchmarks=["BTC buy-and-hold"],
        fee_per_side=GRID_FEE,
    )
    spot = fetch_coinbase_daily("BTC-USD", date(2017, 1, 1))
    starts = _month_starts(spot.index)

    equity = []
    trades = []
    # Process month by month; equity continuous across resets (residual marked then redeployed)
    book = CAPITAL
    for mi, start in enumerate(starts):
        # month end = day before next start, or last bar
        end = starts[mi + 1] - pd.Timedelta(days=1) if mi + 1 < len(starts) else spot.index[-1]
        month = spot.loc[start:end]
        if len(month) < 2:
            continue
        center = float(month["Open"].iloc[0])
        low = center * 0.9
        high = center * 1.1
        # 20 geometric lines between low and high
        levels = [low * (high / low) ** (i / 19) for i in range(20)]
        # equal BTC size per line: allocate book across levels conceptually — buy half grid below mid with cash split
        btc_per_line = (book / center) / 20.0
        cash = book
        inv = 0.0  # btc inventory
        # seed: buy all lines below center at open (classic grid inventory)
        for lv in levels:
            if lv < center and cash > 0:
                cost = btc_per_line * lv
                fee = cost * GRID_FEE
                if cash >= cost + fee:
                    cash -= cost + fee
                    inv += btc_per_line
                    trades.append({"date": str(start.date()), "side": "BUY", "symbol": "BTC", "price": lv, "qty": btc_per_line, "fees": round(fee, 4), "pnl": None, "reason": "grid seed"})
        last_px = center
        for d, row in month.iterrows():
            px = float(row["Close"])
            # cross levels from last_px to px
            if px < last_px:
                for lv in reversed(levels):
                    if px <= lv <= last_px:
                        # buy
                        cost = btc_per_line * lv
                        fee = cost * GRID_FEE
                        if cash >= cost + fee:
                            cash -= cost + fee
                            inv += btc_per_line
                            trades.append({"date": str(d.date()), "side": "BUY", "symbol": "BTC", "price": lv, "qty": btc_per_line, "fees": round(fee, 4), "pnl": None, "reason": "grid buy"})
            elif px > last_px:
                for lv in levels:
                    if last_px <= lv <= px:
                        if inv >= btc_per_line - 1e-12:
                            proceeds = btc_per_line * lv
                            fee = proceeds * GRID_FEE
                            cash += proceeds - fee
                            inv -= btc_per_line
                            trades.append({"date": str(d.date()), "side": "SELL", "symbol": "BTC", "price": lv, "qty": btc_per_line, "fees": round(fee, 4), "pnl": None, "reason": "grid sell"})
            last_px = px
            marked = cash + inv * px
            equity.append({"date": str(d.date()), "equity": round(marked, 2)})
        # month close mark → next book
        book = cash + inv * float(month["Close"].iloc[-1])

    eq_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in equity}).groupby(level=0).last()
    sells = [t for t in trades if t["side"] == "SELL"]
    stats = summarize_backtest(eq_s, [{"pnl": 0.0} for _ in sells], periods_per_year=365)
    stats["trades"] = len(trades)
    stats["win_rate"] = None
    stats["average_trade"] = None
    stats["time_in_market"] = 1.0
    btc_bh = CAPITAL * spot["Close"] / float(spot["Close"].iloc[0])
    stats["benchmark_btc_total_return"] = float(btc_bh.iloc[-1] / CAPITAL - 1)

    folder = HERE / "B-NEW-3"
    write_json(folder / "META.json", meta.to_public())
    write_json(folder / "backtest_stats.json", stats)
    write_csv(folder / "equity_backtest.csv", [{"date": str(k.date()), "equity": float(v)} for k, v in eq_s.items()])
    write_csv(folder / "trades_backtest.csv", trades)

    # Forward: fresh $10,000 book from FORWARD_START (paper tracker start).
    # Center on that day's open; next calendar-month start will reset per rules.
    fwd_dates = [d for d in spot.index if d.date() >= FORWARD_START]
    if not fwd_dates:
        fwd_dates = [spot.index[-1]]
    start = fwd_dates[0]
    center = float(spot["Open"].loc[start])
    low, high = center * 0.9, center * 1.1
    levels = [low * (high / low) ** (i / 19) for i in range(20)]
    btc_per_line = (CAPITAL / center) / 20.0
    cash = CAPITAL
    inv = 0.0
    forward_trades = []
    for lv in levels:
        if lv < center:
            cost = btc_per_line * lv
            fee = cost * GRID_FEE
            if cash >= cost + fee:
                cash -= cost + fee
                inv += btc_per_line
                forward_trades.append({"timestamp": start.isoformat() + "Z", "side": "BUY", "symbol": "BTC", "price": lv, "qty": btc_per_line, "fees": round(fee, 4), "pnl": "", "reason": "forward start grid seed"})
    forward_equity = []
    last_px = center
    b0 = float(spot["Close"].loc[start])
    next_month_starts = set(s for s in starts if s.date() > FORWARD_START)

    def apply_path(px_from: float, px_to: float, d):
        nonlocal cash, inv
        if px_to < px_from:
            for lv in reversed(levels):
                if px_to <= lv <= px_from:
                    cost = btc_per_line * lv
                    fee = cost * GRID_FEE
                    if cash >= cost + fee:
                        cash -= cost + fee
                        inv += btc_per_line
                        forward_trades.append({"timestamp": d.isoformat() + "Z", "side": "BUY", "symbol": "BTC", "price": lv, "qty": btc_per_line, "fees": round(fee, 4), "pnl": "", "reason": "grid buy"})
        elif px_to > px_from:
            for lv in levels:
                if px_from <= lv <= px_to:
                    if inv >= btc_per_line - 1e-12:
                        proceeds = btc_per_line * lv
                        fee = proceeds * GRID_FEE
                        cash += proceeds - fee
                        inv -= btc_per_line
                        forward_trades.append({"timestamp": d.isoformat() + "Z", "side": "SELL", "symbol": "BTC", "price": lv, "qty": btc_per_line, "fees": round(fee, 4), "pnl": "", "reason": "grid sell"})

    for d in fwd_dates:
        if d in next_month_starts:
            # monthly reset: mark book then redeploy fresh CAPITAL-sized grid
            px = float(spot["Close"].loc[d])
            book = cash + inv * px
            cash = book
            inv = 0.0
            center = float(spot["Open"].loc[d])
            low, high = center * 0.9, center * 1.1
            levels = [low * (high / low) ** (i / 19) for i in range(20)]
            btc_per_line = (cash / center) / 20.0
            for lv in levels:
                if lv < center:
                    cost = btc_per_line * lv
                    fee = cost * GRID_FEE
                    if cash >= cost + fee:
                        cash -= cost + fee
                        inv += btc_per_line
                        forward_trades.append({"timestamp": d.isoformat() + "Z", "side": "BUY", "symbol": "BTC", "price": lv, "qty": btc_per_line, "fees": round(fee, 4), "pnl": "", "reason": "monthly grid reset"})
            last_px = center
        px = float(spot["Close"].loc[d])
        apply_path(last_px, px, d)
        last_px = px
        marked = cash + inv * px
        forward_equity.append({"date": str(d.date()), "equity": round(marked, 2), "benchmark_btc": round(CAPITAL * px / b0, 2)})
    if not forward_equity:
        forward_equity = [{"date": FORWARD_START.isoformat(), "equity": CAPITAL, "benchmark_btc": CAPITAL}]
    state = {"cash": round(cash, 2), "btc": inv, "center": center, "band": [low, high], "levels": 20, "as_of": forward_equity[-1]["date"], "experiment_label": EXPERIMENT_LABEL, "id": meta.id}
    write_csv(folder / "forward" / "equity.csv", forward_equity)
    write_csv(folder / "forward" / "trades.csv", forward_trades, fieldnames=["timestamp", "side", "symbol", "price", "qty", "fees", "pnl", "reason"])
    write_json(folder / "forward" / "state.json", state)
    return {"meta": meta.to_public(), "stats": stats, "forward": forward_equity[-1], "state": state}


def run_b_new_4() -> dict:
    """BTC/ETH Band Rebalance — allocation-control experiment. Frozen before inspecting results."""
    meta = StrategyMeta(
        id="B-NEW-4",
        name="BTC/ETH Band Rebalance",
        category="Crypto Bot",
        source="https://corporate.vanguard.com/content/dam/corp/research/pdf/rational_rebalancing_analytical_approach_to_multiasset_portfolio_rebalancing.pdf",
        why="Allocation-control test: does a 40/60 band around a 50/50 BTC–ETH book change exposure, turnover, and risk versus letting weights drift or rebalancing on a calendar? Rules frozen from the band-rebalancing idea before inspecting results.",
        why_fail="Crypto gaps can blow through bands between daily closes; 1.5× crypto fees make frequent rebalances costly; two-asset spot books ignore stablecoin/cash sleeves and exchange risk.",
        rules=[
            "Start at 50% BTC and 50% ETH using Coinbase spot USD pairs (BTC-USD, ETH-USD).",
            "After each completed UTC day, measure portfolio weights from that day’s closes only.",
            "If BTC’s weight is below 40% or above 60%, submit a simulated rebalance back to 50/50 at the next bar’s open (previously completed data only).",
            "Otherwise hold.",
            f"Cost: {CRYPTO_FEE*100:.3f}% per side (1.5× desk crypto 0.25%). Also report doubled-cost results.",
            "Benchmarks (same feed, start, execution assumptions, cost model): (1) buy-and-hold 50/50 with drift; (2) calendar-monthly rebalance to 50/50 at month-start open.",
            "Long-only, unleveraged, paper only. No exchange credentials.",
        ],
        benchmarks=["50/50 buy-and-hold (drift)", "Calendar-monthly 50/50 rebalance"],
        fee_per_side=CRYPTO_FEE,
    )
    data_source = "Coinbase Exchange public daily candles (BTC-USD, ETH-USD)"
    btc = fetch_coinbase_daily("BTC-USD", date(2017, 1, 1))
    eth = fetch_coinbase_daily("ETH-USD", date(2017, 1, 1))
    idx = btc.index.intersection(eth.index).sort_values()
    btc = btc.loc[idx]
    eth = eth.loc[idx]
    month_starts = set(_month_starts(idx))

    if len(idx) < 60:
        folder = HERE / "B-NEW-4"
        stats = {
            "label": "Historical backtest, not forward results",
            "awaiting_verified_historical_data": True,
            "reason": "Insufficient Coinbase daily coverage for BTC and ETH to warm up and hold out a chronological sample.",
            "data_source": data_source,
            "cagr": None,
            "sharpe": None,
            "max_drawdown": None,
            "trades": None,
            "over_10pct_dd": None,
            "crash_periods": {},
            "start": None,
            "end": None,
        }
        write_json(folder / "META.json", meta.to_public())
        write_json(folder / "backtest_stats.json", stats)
        write_forward_ledger(
            folder,
            [{"date": FORWARD_START.isoformat(), "equity": CAPITAL, "benchmark_drift": CAPITAL, "benchmark_monthly": CAPITAL}],
            [],
            {
                "cash": 0.0,
                "btc": 0.0,
                "eth": 0.0,
                "as_of": None,
                "exposure": 0.0,
                "btc_weight": None,
                "eth_weight": None,
                "last_signal": "awaiting",
                "status": "Awaiting first mark",
                "data_failure": stats["reason"],
                "experiment_label": EXPERIMENT_LABEL,
                "id": meta.id,
            },
        )
        return {"meta": meta.to_public(), "stats": stats, "forward": {"equity": CAPITAL}, "state": {}}

    def simulate(fee: float, start: pd.Timestamp, end: pd.Timestamp):
        use = idx[(idx >= start) & (idx <= end)]
        if len(use) < 2:
            return {
                "equity": [],
                "trades": [],
                "drift": [],
                "monthly": [],
                "weight_rows": [],
                "data_failures": ["Window too short"],
                "last_signal": "awaiting",
                "last_decision": None,
                "btc": 0.0,
                "eth": 0.0,
                "skipped": 0,
            }
        trades = []
        equity = []
        drift_eq = []
        monthly_eq = []
        weight_rows = []
        data_failures = []
        skipped = 0
        last_signal = "hold"
        last_decision = None
        pending_band = False  # rebalance at next open

        def open_px(d, which):
            row = btc.loc[d] if which == "BTC" else eth.loc[d]
            return float(row["Open"])

        def close_px(d, which):
            row = btc.loc[d] if which == "BTC" else eth.loc[d]
            return float(row["Close"])

        d0 = use[0]
        # Seed 50/50 at first open
        try:
            b_o = open_px(d0, "BTC")
            e_o = open_px(d0, "ETH")
        except Exception as err:
            return {
                "equity": [],
                "trades": [],
                "drift": [],
                "monthly": [],
                "weight_rows": [],
                "data_failures": [f"Missing opens at {d0.date()}: {err}"],
                "last_signal": "awaiting",
                "last_decision": None,
                "btc": 0.0,
                "eth": 0.0,
                "skipped": 1,
            }
        # Band book
        half = CAPITAL * 0.5
        fee_b = half * fee
        fee_e = half * fee
        btc_u = (half - fee_b) / b_o
        eth_u = (half - fee_e) / e_o
        trades.append({"date": str(d0.date()), "side": "BUY", "symbol": "BTC", "price": b_o, "qty": btc_u, "fees": round(fee_b, 4), "pnl": None, "reason": "seed 50%"})
        trades.append({"date": str(d0.date()), "side": "BUY", "symbol": "ETH", "price": e_o, "qty": eth_u, "fees": round(fee_e, 4), "pnl": None, "reason": "seed 50%"})
        # Drift book (same seed, never rebalances)
        d_btc, d_eth = btc_u, eth_u
        # Monthly book
        m_btc, m_eth = btc_u, eth_u

        for i, d in enumerate(use):
            # Execute pending band rebalance at open (decision from prior completed day)
            if pending_band and i > 0:
                try:
                    b_o = open_px(d, "BTC")
                    e_o = open_px(d, "ETH")
                except Exception:
                    data_failures.append(f"{d.date()}: missing open for band rebalance; skipped")
                    skipped += 1
                    pending_band = False
                else:
                    # Mark value at open, then reset to 50/50
                    port = btc_u * b_o + eth_u * e_o
                    # Sell all
                    for sym, units, px in (("BTC", btc_u, b_o), ("ETH", eth_u, e_o)):
                        if units <= 0:
                            continue
                        proceeds = units * px
                        f = proceeds * fee
                        trades.append({"date": str(d.date()), "side": "SELL", "symbol": sym, "price": px, "qty": units, "fees": round(f, 4), "pnl": None, "reason": "band rebalance exit"})
                    # Buy 50/50
                    half = port  # fees taken on sells already reduced? use post-sell cash
                    cash = (btc_u * b_o) * (1 - fee) + (eth_u * e_o) * (1 - fee)
                    half = cash * 0.5
                    fee_b = half * fee
                    fee_e = half * fee
                    btc_u = (half - fee_b) / b_o
                    eth_u = (half - fee_e) / e_o
                    trades.append({"date": str(d.date()), "side": "BUY", "symbol": "BTC", "price": b_o, "qty": btc_u, "fees": round(fee_b, 4), "pnl": None, "reason": "band rebalance to 50/50"})
                    trades.append({"date": str(d.date()), "side": "BUY", "symbol": "ETH", "price": e_o, "qty": eth_u, "fees": round(fee_e, 4), "pnl": None, "reason": "band rebalance to 50/50"})
                    last_signal = "rebalance"
                    last_decision = {"date": str(d.date()), "action": "rebalance_50_50", "trigger": "BTC weight outside 40–60% on prior close"}
                    pending_band = False

            # Calendar monthly rebalance at month-start open (benchmark)
            if d in month_starts and i > 0:
                try:
                    b_o = open_px(d, "BTC")
                    e_o = open_px(d, "ETH")
                    cash_m = m_btc * b_o * (1 - fee) + m_eth * e_o * (1 - fee)
                    half = cash_m * 0.5
                    m_btc = (half - half * fee) / b_o
                    m_eth = (half - half * fee) / e_o
                except Exception:
                    data_failures.append(f"{d.date()}: monthly bench open missing; skipped monthly rebalance mark")

            # End-of-day marks from completed closes
            try:
                b_c = close_px(d, "BTC")
                e_c = close_px(d, "ETH")
            except Exception:
                data_failures.append(f"{d.date()}: missing close; skipped mark")
                skipped += 1
                continue
            port = btc_u * b_c + eth_u * e_c
            w_btc = (btc_u * b_c / port) if port else 0.5
            w_eth = 1.0 - w_btc
            equity.append({"date": str(d.date()), "equity": round(port, 2)})
            drift_eq.append({"date": str(d.date()), "equity": round(d_btc * b_c + d_eth * e_c, 2)})
            monthly_eq.append({"date": str(d.date()), "equity": round(m_btc * b_c + m_eth * e_c, 2)})
            weight_rows.append({"date": str(d.date()), "btc_weight": round(w_btc, 6), "eth_weight": round(w_eth, 6)})

            # Decision after completed day → next bar open
            if w_btc < 0.40 or w_btc > 0.60:
                pending_band = True
                last_signal = "band_breach"
                last_decision = {
                    "signal_date": str(d.date()),
                    "btc_weight": round(w_btc, 4),
                    "eth_weight": round(w_eth, 4),
                    "action": "queue_rebalance_next_open",
                }
            elif last_signal != "rebalance":
                last_signal = "hold"
                last_decision = {
                    "signal_date": str(d.date()),
                    "btc_weight": round(w_btc, 4),
                    "eth_weight": round(w_eth, 4),
                    "action": "hold_inside_band",
                }

        return {
            "equity": equity,
            "trades": trades,
            "drift": drift_eq,
            "monthly": monthly_eq,
            "weight_rows": weight_rows,
            "data_failures": data_failures,
            "last_signal": last_signal,
            "last_decision": last_decision,
            "btc": btc_u,
            "eth": eth_u,
            "skipped": skipped,
        }

    # Holdout: from first bar 2017 (warm-up none beyond seed) through day before FORWARD_START
    holdout_start = idx[0]
    holdout_end_list = [d for d in idx if d.date() < FORWARD_START]
    holdout_end = holdout_end_list[-1] if holdout_end_list else idx[-1]
    base = simulate(CRYPTO_FEE, holdout_start, holdout_end)
    doubled = simulate(CRYPTO_FEE * 2.0, holdout_start, holdout_end)

    eq_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in base["equity"]})
    drift_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in base["drift"]})
    monthly_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in base["monthly"]})
    closed = [{"pnl": 0.0} for t in base["trades"] if t["side"] == "SELL"]
    stats = summarize_backtest(eq_s, closed, periods_per_year=365) if len(eq_s) >= 2 else {
        "label": "Historical backtest, not forward results",
        "awaiting_verified_historical_data": True,
        "reason": "Holdout equity path too short.",
        "cagr": None,
        "sharpe": None,
        "max_drawdown": None,
        "trades": None,
        "over_10pct_dd": None,
        "crash_periods": {},
        "start": None,
        "end": None,
    }
    if len(eq_s) >= 2:
        stats["data_source"] = data_source
        stats["holdout_start"] = str(holdout_start.date())
        stats["holdout_end"] = str(holdout_end.date())
        stats["fill_count"] = len(base["trades"])
        stats["trades"] = sum(1 for t in base["trades"] if t["side"] in ("BUY", "SELL"))
        raw_to = turnover_from_trades(base["trades"])
        years = max(len(eq_s) / 365.0, 1e-9)
        stats["turnover"] = raw_to / years  # average one-way turnover per year vs initial capital
        stats["turnover_total"] = raw_to
        stats["win_rate"] = None
        stats["average_trade"] = None
        stats["time_in_market"] = 1.0
        if len(drift_s) >= 2:
            stats["benchmark_drift_total_return"] = float(drift_s.iloc[-1] / CAPITAL - 1)
            stats["benchmark_drift_max_drawdown"] = max_drawdown(drift_s)
            stats["benchmark_gap_vs_drift"] = float(eq_s.iloc[-1] / CAPITAL - drift_s.iloc[-1] / CAPITAL)
        if len(monthly_s) >= 2:
            stats["benchmark_monthly_total_return"] = float(monthly_s.iloc[-1] / CAPITAL - 1)
            stats["benchmark_monthly_max_drawdown"] = max_drawdown(monthly_s)
            stats["benchmark_gap_vs_monthly"] = float(eq_s.iloc[-1] / CAPITAL - monthly_s.iloc[-1] / CAPITAL)
        if base["weight_rows"]:
            drifts = [abs(r["btc_weight"] - 0.5) for r in base["weight_rows"]]
            stats["weight_drift_avg_abs"] = float(np.mean(drifts))
            stats["weight_drift_max_abs"] = float(np.max(drifts))
            stats["band_breach_days"] = int(sum(1 for r in base["weight_rows"] if r["btc_weight"] < 0.40 or r["btc_weight"] > 0.60))
        dbl_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in doubled["equity"]})
        if len(dbl_s) >= 2:
            stats["doubled_cost_total_return"] = float(dbl_s.iloc[-1] / CAPITAL - 1)
            stats["doubled_cost_max_drawdown"] = max_drawdown(dbl_s)
            stats["doubled_cost_fill_count"] = len(doubled["trades"])
        stats["vs_published_research"] = (
            "Vanguard’s rational-rebalancing note studies multi-asset band vs calendar rebalancing "
            "for traditional portfolios. This experiment applies a fixed 10-percentage-point band "
            "around 50/50 on BTC/ETH spot only, with next-bar-open execution after a completed UTC "
            "day and 1.5× crypto costs. It is an allocation-control test, not a return forecast."
        )

    folder = HERE / "B-NEW-4"
    write_json(folder / "META.json", meta.to_public())
    write_json(folder / "backtest_stats.json", stats)
    write_csv(folder / "equity_backtest.csv", base["equity"])
    write_csv(folder / "trades_backtest.csv", base["trades"])
    write_csv(folder / "comparisons" / "drift_equity.csv", base["drift"])
    write_csv(folder / "comparisons" / "monthly_equity.csv", base["monthly"])
    write_csv(folder / "comparisons" / "weights.csv", base["weight_rows"])
    write_csv(folder / "comparisons" / "doubled_cost_equity.csv", doubled["equity"])

    # Forward from FORWARD_START
    fwd_idx = idx[idx.date >= FORWARD_START]
    if len(fwd_idx) == 0:
        fwd_idx = idx[-1:]
    fwd = simulate(CRYPTO_FEE, fwd_idx[0], fwd_idx[-1])
    forward_trades = []
    for t in fwd["trades"]:
        forward_trades.append(
            {
                "timestamp": f"{t['date']}T00:00:00Z",
                "side": t["side"],
                "symbol": t["symbol"],
                "price": t["price"],
                "qty": t["qty"],
                "fees": t["fees"],
                "pnl": "" if t.get("pnl") is None else t["pnl"],
                "reason": t["reason"],
            }
        )
    forward_equity = []
    for i, r in enumerate(fwd["equity"]):
        forward_equity.append(
            {
                "date": r["date"],
                "equity": r["equity"],
                "benchmark_drift": fwd["drift"][i]["equity"] if i < len(fwd["drift"]) else CAPITAL,
                "benchmark_monthly": fwd["monthly"][i]["equity"] if i < len(fwd["monthly"]) else CAPITAL,
            }
        )
    if not forward_equity:
        forward_equity = [
            {
                "date": FORWARD_START.isoformat(),
                "equity": CAPITAL,
                "benchmark_drift": CAPITAL,
                "benchmark_monthly": CAPITAL,
            }
        ]

    last = forward_equity[-1]
    port = last["equity"] or CAPITAL
    # weights from last weight row if any
    btc_w = fwd["weight_rows"][-1]["btc_weight"] if fwd["weight_rows"] else 0.5
    eth_w = fwd["weight_rows"][-1]["eth_weight"] if fwd["weight_rows"] else 0.5
    exposure = 1.0  # always fully invested long-only
    status = classify_status(
        as_of=last["date"],
        exposure=exposure,
        last_signal=fwd["last_signal"],
        data_failure="; ".join(fwd["data_failures"][-3:]) if fwd["skipped"] and not fwd["equity"] else None,
        category="Crypto Bot",
    )
    state = {
        "cash": 0.0,
        "btc": fwd["btc"],
        "eth": fwd["eth"],
        "as_of": last["date"],
        "exposure": exposure,
        "btc_weight": btc_w,
        "eth_weight": eth_w,
        "last_signal": fwd["last_signal"],
        "last_decision": fwd["last_decision"],
        "status": status,
        "data_failures": fwd["data_failures"][-10:],
        "data_source": data_source,
        "experiment_label": EXPERIMENT_LABEL,
        "id": meta.id,
    }
    write_forward_ledger(folder, forward_equity, forward_trades, state)
    return {"meta": meta.to_public(), "stats": stats, "forward": forward_equity[-1], "state": state}
