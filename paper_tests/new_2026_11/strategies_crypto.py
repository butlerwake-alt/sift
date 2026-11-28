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
    fetch_coinbase_daily,
    fetch_deribit_funding,
    load_yahoo,
    max_drawdown,
    summarize_backtest,
    write_csv,
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
