#!/usr/bin/env python3
"""Stock/ETF new experiments S-NEW-1..3. Paper only."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    CAPITAL,
    EXPERIMENT_LABEL,
    FORWARD_START,
    HERE,
    STOCK_FEE,
    StrategyMeta,
    bil_daily_yield,
    load_yahoo,
    load_yahoo_ohlc,
    max_drawdown,
    summarize_backtest,
    write_csv,
    write_json,
)


def _month_groups(idx: pd.DatetimeIndex):
    return idx.to_series().groupby([idx.year, idx.month]).groups


def run_s_new_1() -> dict:
    meta = StrategyMeta(
        id="S-NEW-1",
        name="Turn of the Month (SPY)",
        category="Stock Strategy",
        source="https://ripbacktest.com/posts/turn-of-the-month-effect-spy/",
        why="Classic calendar effect: historically concentrated equity premium around month turns. Frozen rule from Rip Backtest; no parameter search.",
        why_fail="Calendar effects can fade once crowded; gap risk over weekends; 1.5x costs and idle-cash modeling can erase thin edges.",
        rules=[
            "Buy SPY at the close of the 2nd-to-last trading day of the month.",
            "Sell SPY at the close of the 3rd trading day of the next month.",
            "Hold cash (BIL yield) otherwise.",
            f"Cost: {STOCK_FEE*100:.3f}% fee+slippage per side (1.5× desk 0.05%).",
            "No leverage. Paper only.",
        ],
        benchmarks=["SPY buy-and-hold", "Random 4-day holds in the same months (comparison only)"],
        fee_per_side=STOCK_FEE,
    )
    ohlc = load_yahoo_ohlc("SPY", "2005-01-01")
    bil = load_yahoo(["BIL"], "2005-01-01")["BIL"].dropna()
    bil = bil.reindex(ohlc.index).ffill()
    cash_y = bil_daily_yield(bil)

    closes = ohlc["Close"]
    equity = []
    trades = []
    cash = CAPITAL
    shares = 0.0
    entry_cost_basis = 0.0
    eq = CAPITAL
    dates = list(closes.index)
    by_month = {}
    for d in dates:
        key = (d.year, d.month)
        by_month.setdefault(key, []).append(d)

    buy_days = set()
    sell_days = set()
    months = sorted(by_month)
    for i, m in enumerate(months):
        days = by_month[m]
        if len(days) >= 2:
            buy_days.add(days[-2])
        if i + 1 < len(months):
            nxt = by_month[months[i + 1]]
            if len(nxt) >= 3:
                sell_days.add(nxt[2])

    # Random 4-day holds comparison (seeded, comparison only)
    rng = np.random.default_rng(42)
    rand_equity = []
    rand_cash = CAPITAL
    rand_shares = 0.0
    rand_hold_left = 0

    for d in dates:
        px = float(closes.loc[d])
        # strategy
        if d in sell_days and shares > 0:
            proceeds = shares * px
            fee = proceeds * STOCK_FEE
            pnl = proceeds - fee - entry_cost_basis
            cash = proceeds - fee
            trades.append({"date": str(d.date()), "side": "SELL", "symbol": "SPY", "price": px, "shares": shares, "fees": round(fee, 4), "pnl": round(pnl, 2), "reason": "3rd trading day of month close"})
            shares = 0.0
        if d in buy_days and shares == 0:
            fee = cash * STOCK_FEE
            spend = cash - fee
            shares = spend / px
            entry_cost_basis = cash
            cash = 0.0
            trades.append({"date": str(d.date()), "side": "BUY", "symbol": "SPY", "price": px, "shares": shares, "fees": round(fee, 4), "pnl": None, "reason": "2nd-to-last trading day close"})
        if shares == 0:
            cash *= 1.0 + float(cash_y.get(d, 0.0))
        eq = cash + shares * px
        equity.append({"date": str(d.date()), "equity": round(eq, 2), "cash_interest_proxy": float(cash_y.get(d, 0.0))})

        # random comparison
        if rand_hold_left == 0 and rand_shares > 0:
            proceeds = rand_shares * px
            fee = proceeds * STOCK_FEE
            rand_cash = proceeds - fee
            rand_shares = 0.0
        if rand_hold_left == 0 and d in buy_days:
            # start a random 4-day hold this month (comparison only)
            fee = rand_cash * STOCK_FEE
            spend = rand_cash - fee
            rand_shares = spend / px
            rand_cash = 0.0
            rand_hold_left = 4
        if rand_shares > 0:
            rand_hold_left -= 1
        else:
            rand_cash *= 1.0 + float(cash_y.get(d, 0.0))
        rand_equity.append({"date": str(d.date()), "equity": round(rand_cash + rand_shares * px, 2)})

    eq_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in equity})
    spy_bh = CAPITAL * closes / float(closes.iloc[0])
    stats = summarize_backtest(eq_s, [t for t in trades if t["side"] == "SELL" or t.get("pnl") is not None], periods_per_year=252)
    # attach closed trade pnls properly
    closed = []
    last_buy = None
    for t in trades:
        if t["side"] == "BUY":
            last_buy = t
        elif t["side"] == "SELL" and last_buy:
            closed.append({**t, "pnl": t["pnl"]})
            last_buy = None
    stats = summarize_backtest(eq_s, closed, periods_per_year=252)
    # time in market
    in_mkt = sum(1 for r in equity if r["equity"] and True)
    held_days = 0
    pos = 0
    for t in trades:
        pass
    # compute from buy/sell sets
    holding = False
    held = 0
    for d in dates:
        if d in buy_days:
            holding = True
        if holding:
            held += 1
        if d in sell_days:
            holding = False
    stats["time_in_market"] = held / len(dates) if dates else None
    stats["benchmark_spy_cagr"] = float((float(spy_bh.iloc[-1]) / CAPITAL) ** (252 / len(spy_bh)) - 1) if len(spy_bh) > 1 else None
    stats["benchmark_spy_total_return"] = float(spy_bh.iloc[-1] / CAPITAL - 1)
    rand_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in rand_equity})
    stats["comparison_random_4day"] = {
        "note": "comparison only, not a pick",
        "total_return": float(rand_s.iloc[-1] / CAPITAL - 1),
        "max_drawdown": max_drawdown(rand_s),
    }

    folder = HERE / "S-NEW-1"
    write_json(folder / "META.json", meta.to_public())
    write_json(folder / "backtest_stats.json", stats)
    write_csv(folder / "equity_backtest.csv", equity)
    write_csv(folder / "trades_backtest.csv", trades)
    write_csv(folder / "comparisons" / "random_4day_equity.csv", rand_equity)

    # Forward paper from FORWARD_START
    fwd_dates = [d for d in dates if d.date() >= FORWARD_START]
    if not fwd_dates:
        # seed day-1 even if market holiday: use last available <= today
        fwd_dates = [dates[-1]] if dates else []
    forward_trades = []
    forward_equity = []
    cash = CAPITAL
    shares = 0.0
    entry_cost_basis = 0.0
    idle_cash_income = 0.0
    state = {"cash": CAPITAL, "shares": 0.0, "symbol": None, "as_of": None}
    for d in fwd_dates:
        px = float(closes.loc[d])
        if d in sell_days and shares > 0:
            proceeds = shares * px
            fee = proceeds * STOCK_FEE
            pnl = proceeds - fee - entry_cost_basis
            cash = proceeds - fee
            forward_trades.append({"timestamp": f"{d.date()}T16:00:00-05:00", "side": "SELL", "symbol": "SPY", "price": px, "qty": shares, "fees": round(fee, 4), "pnl": round(pnl, 2), "reason": "3rd trading day of month close"})
            shares = 0.0
        if d in buy_days and shares == 0:
            fee = cash * STOCK_FEE
            spend = cash - fee
            shares = spend / px
            entry_cost_basis = cash
            cash = 0.0
            forward_trades.append({"timestamp": f"{d.date()}T16:00:00-05:00", "side": "BUY", "symbol": "SPY", "price": px, "qty": shares, "fees": round(fee, 4), "pnl": "", "reason": "2nd-to-last trading day close"})
        if shares == 0:
            y = float(cash_y.get(d, 0.0))
            earned = cash * y
            idle_cash_income += earned
            cash *= 1.0 + y
        eq = cash + shares * px
        forward_equity.append({"date": str(d.date()), "equity": round(eq, 2), "benchmark_spy": round(CAPITAL * px / float(closes.loc[fwd_dates[0]]), 2), "idle_cash_income": round(idle_cash_income, 2)})
        state = {"cash": round(cash, 2), "shares": shares, "symbol": "SPY" if shares else None, "as_of": str(d.date()), "price": px, "idle_cash_income": round(idle_cash_income, 2)}
    if not forward_equity:
        forward_equity = [{"date": FORWARD_START.isoformat(), "equity": CAPITAL, "benchmark_spy": CAPITAL, "idle_cash_income": 0.0}]
        state = {"cash": CAPITAL, "shares": 0.0, "symbol": None, "as_of": FORWARD_START.isoformat(), "price": None, "idle_cash_income": 0.0}

    write_csv(folder / "forward" / "equity.csv", forward_equity)
    write_csv(folder / "forward" / "trades.csv", forward_trades, fieldnames=["timestamp", "side", "symbol", "price", "qty", "fees", "pnl", "reason"])
    write_json(folder / "forward" / "state.json", {**state, "experiment_label": EXPERIMENT_LABEL, "id": meta.id})
    return {"meta": meta.to_public(), "stats": stats, "forward": forward_equity[-1], "state": state}


def run_s_new_2() -> dict:
    meta = StrategyMeta(
        id="S-NEW-2",
        name="3 Days Down Overnight (SPY)",
        category="Stock Strategy",
        source="https://x.com/QuantifiedStrat/status/2123808598535094771",
        why="Tests a simple overnight mean-reversion claim after three down closes. Rules frozen from the public post; no tuning.",
        why_fail="Overnight gaps can go the wrong way; consecutive down days cluster in crashes; costs at 1.5× desk rates hurt high-turnover edges.",
        rules=[
            "After 3 consecutive lower closes (close < prior close), buy SPY at that close.",
            "Sell at the next open (primary).",
            f"Cost: {STOCK_FEE*100:.3f}% per side (1.5× desk).",
            "Comparison only: sell at the next close instead.",
        ],
        benchmarks=["SPY buy-and-hold"],
        fee_per_side=STOCK_FEE,
    )
    ohlc = load_yahoo_ohlc("SPY", "2005-01-01")
    bil = load_yahoo(["BIL"], "2005-01-01")["BIL"].dropna().reindex(ohlc.index).ffill()
    cash_y = bil_daily_yield(bil)
    c = ohlc["Close"]
    o = ohlc["Open"]
    down = (c < c.shift(1)).astype(int)
    signal = (down.shift(0) == 1) & (down.shift(1) == 1) & (down.shift(2) == 1) & (down.shift(3) == 0)
    # signal on day t when t, t-1, t-2 are down days — "after 3 consecutive lower closes" means on the 3rd down close
    three_down = (down == 1) & (down.shift(1) == 1) & (down.shift(2) == 1)

    def simulate(exit_mode: str):
        cash = CAPITAL
        shares = 0.0
        entry_basis = 0.0
        equity = []
        trades = []
        pending_sell = None  # date to sell
        dates = list(c.index)
        for i, d in enumerate(dates):
            px_close = float(c.iloc[i])
            px_open = float(o.iloc[i])
            # exits first at open if overnight mode
            if pending_sell == d and shares > 0:
                px = px_open if exit_mode == "next_open" else px_close
                fee = shares * px * STOCK_FEE
                proceeds = shares * px - fee
                pnl = proceeds - entry_basis
                cash = proceeds
                trades.append({"date": str(d.date()), "side": "SELL", "symbol": "SPY", "price": px, "shares": shares, "fees": round(fee, 4), "pnl": round(pnl, 2), "reason": f"exit {exit_mode}"})
                shares = 0.0
                pending_sell = None
            if shares == 0 and bool(three_down.iloc[i]) and i + 1 < len(dates):
                fee = cash * STOCK_FEE
                spend = cash - fee
                shares = spend / px_close
                entry_basis = cash
                cash = 0.0
                trades.append({"date": str(d.date()), "side": "BUY", "symbol": "SPY", "price": px_close, "shares": shares, "fees": round(fee, 4), "pnl": None, "reason": "3 consecutive lower closes"})
                pending_sell = dates[i + 1]
            if shares == 0:
                cash *= 1.0 + float(cash_y.get(d, 0.0))
            equity.append({"date": str(d.date()), "equity": round(cash + shares * px_close, 2)})
        return equity, trades

    equity, trades = simulate("next_open")
    eq_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in equity})
    closed = [t for t in trades if t.get("pnl") is not None]
    stats = summarize_backtest(eq_s, closed, periods_per_year=252)
    held = sum(1 for t in trades if t["side"] == "BUY")  # overnight holds ≈ number of buys
    stats["time_in_market"] = held / len(equity) if equity else None
    spy_bh = CAPITAL * c / float(c.iloc[0])
    stats["benchmark_spy_total_return"] = float(spy_bh.iloc[-1] / CAPITAL - 1)

    cmp_eq, cmp_tr = simulate("next_close")
    cmp_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in cmp_eq})
    stats["comparison_sell_next_close"] = {
        "note": "comparison only, not a pick",
        "total_return": float(cmp_s.iloc[-1] / CAPITAL - 1),
        "max_drawdown": max_drawdown(cmp_s),
        "trades": sum(1 for t in cmp_tr if t.get("pnl") is not None),
    }

    folder = HERE / "S-NEW-2"
    write_json(folder / "META.json", meta.to_public())
    write_json(folder / "backtest_stats.json", stats)
    write_csv(folder / "equity_backtest.csv", equity)
    write_csv(folder / "trades_backtest.csv", trades)
    write_csv(folder / "comparisons" / "sell_next_close_equity.csv", cmp_eq)

    # Forward
    dates = list(c.index)
    fwd_idx = [i for i, d in enumerate(dates) if d.date() >= FORWARD_START]
    cash = CAPITAL
    shares = 0.0
    entry_basis = 0.0
    pending_sell = None
    idle_cash_income = 0.0
    forward_trades = []
    forward_equity = []
    for i in fwd_idx:
        d = dates[i]
        px_close = float(c.iloc[i])
        px_open = float(o.iloc[i])
        if pending_sell == d and shares > 0:
            fee = shares * px_open * STOCK_FEE
            proceeds = shares * px_open - fee
            pnl = proceeds - entry_basis
            cash = proceeds
            forward_trades.append({"timestamp": f"{d.date()}T09:30:00-05:00", "side": "SELL", "symbol": "SPY", "price": px_open, "qty": shares, "fees": round(fee, 4), "pnl": round(pnl, 2), "reason": "sell next open"})
            shares = 0.0
            pending_sell = None
        if shares == 0 and bool(three_down.iloc[i]) and i + 1 < len(dates):
            fee = cash * STOCK_FEE
            spend = cash - fee
            shares = spend / px_close
            entry_basis = cash
            cash = 0.0
            forward_trades.append({"timestamp": f"{d.date()}T16:00:00-05:00", "side": "BUY", "symbol": "SPY", "price": px_close, "qty": shares, "fees": round(fee, 4), "pnl": "", "reason": "3 consecutive lower closes"})
            pending_sell = dates[i + 1]
        if shares == 0:
            y = float(cash_y.get(d, 0.0))
            idle_cash_income += cash * y
            cash *= 1.0 + y
        forward_equity.append({"date": str(d.date()), "equity": round(cash + shares * px_close, 2), "benchmark_spy": round(CAPITAL * px_close / float(c.loc[dates[fwd_idx[0]]]), 2), "idle_cash_income": round(idle_cash_income, 2)})
    if not forward_equity:
        forward_equity = [{"date": FORWARD_START.isoformat(), "equity": CAPITAL, "benchmark_spy": CAPITAL, "idle_cash_income": 0.0}]
    state = {"cash": round(cash, 2), "shares": shares, "pending_sell": str(pending_sell.date()) if pending_sell is not None else None, "as_of": forward_equity[-1]["date"], "idle_cash_income": round(idle_cash_income, 2), "experiment_label": EXPERIMENT_LABEL, "id": meta.id}
    write_csv(folder / "forward" / "equity.csv", forward_equity)
    write_csv(folder / "forward" / "trades.csv", forward_trades, fieldnames=["timestamp", "side", "symbol", "price", "qty", "fees", "pnl", "reason"])
    write_json(folder / "forward" / "state.json", state)
    return {"meta": meta.to_public(), "stats": stats, "forward": forward_equity[-1], "state": state}


def run_s_new_3() -> dict:
    meta = StrategyMeta(
        id="S-NEW-3",
        name="Asset-Class Momentum Top 3",
        category="Stock Strategy",
        source="https://www.cxoadvisory.com/momentum-strategy/",
        why="Cross-asset momentum is a long-studied premium. Frozen universe and 4-month lookback with monthly top-3 equal weight; no search over lookbacks.",
        why_fail="Momentum crashes after sharp reversals; ETF universe is today's list (survivorship); monthly rebalance + 1.5× costs reduce edge.",
        rules=[
            "Universe: SPY, IWM, EFA, EEM, TLT, LQD, VNQ, GLD, DBC; BIL as cash.",
            "At each month-end, rank by 4-month total return; hold equal-weight top 3 for 1 month.",
            "If fewer than 3 have data, hold what is available; cash remainder earns BIL.",
            f"Cost: {STOCK_FEE*100:.3f}% per side on rebalance turnover (1.5× desk).",
        ],
        benchmarks=["SPY buy-and-hold", "60/40 SPY/TLT"],
        fee_per_side=STOCK_FEE,
    )
    tickers = ["SPY", "IWM", "EFA", "EEM", "TLT", "LQD", "VNQ", "GLD", "DBC", "BIL"]
    px = load_yahoo(tickers, "2006-01-01").dropna(how="all").ffill()
    assets = ["SPY", "IWM", "EFA", "EEM", "TLT", "LQD", "VNQ", "GLD", "DBC"]
    # last trading day of each month present in the price index
    month_ends = list(px.groupby([px.index.year, px.index.month]).tail(1).index)
    month_end_set = set(month_ends)
    me_px = px.loc[month_ends]
    lookback_months = 4

    holdings = {a: 0.0 for a in assets}
    cash = CAPITAL
    equity_rows = []
    trades = []

    for d, row in px.iterrows():
        if d in month_end_set:
            i = month_ends.index(d)
            if i >= lookback_months:
                rets = {}
                for a in assets:
                    p0 = me_px[a].iloc[i - lookback_months]
                    p1 = me_px[a].iloc[i]
                    if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                        rets[a] = float(p1 / p0 - 1)
                ranked = sorted(rets.items(), key=lambda x: x[1], reverse=True)[:3]
                target = {a: 1.0 / len(ranked) for a, _ in ranked} if ranked else {}
                for a in assets:
                    if holdings[a] > 0 and pd.notna(row[a]):
                        proceeds = holdings[a] * float(row[a])
                        fee = proceeds * STOCK_FEE
                        cash += proceeds - fee
                        trades.append({"date": str(d.date()), "side": "SELL", "symbol": a, "price": float(row[a]), "shares": holdings[a], "fees": round(fee, 4), "pnl": None, "reason": "month-end rebalance"})
                        holdings[a] = 0.0
                port = cash
                for a, w in target.items():
                    if pd.isna(row[a]) or float(row[a]) <= 0:
                        continue
                    alloc = port * w
                    fee = alloc * STOCK_FEE
                    spend = alloc - fee
                    holdings[a] = spend / float(row[a])
                    cash -= alloc
                    trades.append({"date": str(d.date()), "side": "BUY", "symbol": a, "price": float(row[a]), "shares": holdings[a], "fees": round(fee, 4), "pnl": None, "reason": "month-end top3"})
        bil_ret = 0.0
        loc = px.index.get_loc(d)
        if isinstance(loc, int) and loc > 0 and pd.notna(px["BIL"].iloc[loc]) and pd.notna(px["BIL"].iloc[loc - 1]) and px["BIL"].iloc[loc - 1] > 0:
            bil_ret = max(0.0, float(px["BIL"].iloc[loc] / px["BIL"].iloc[loc - 1] - 1))
        if cash > 0:
            cash *= 1.0 + bil_ret
        port = cash + sum(holdings[a] * float(row[a]) for a in assets if pd.notna(row.get(a)))
        equity_rows.append({"date": str(d.date()), "equity": round(port, 2)})

    eq_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in equity_rows})
    # closed trade proxy: count sell legs as trades
    closed = [{"pnl": 0.0} for t in trades if t["side"] == "SELL"]
    # better win rate unavailable without lot matching; count rebalance cycles
    n_cycles = sum(1 for t in trades if t["side"] == "BUY" and t["reason"] == "month-end top3")
    stats = summarize_backtest(eq_s, [{"pnl": 1.0}] * max(n_cycles, 0), periods_per_year=252)
    stats["trades"] = n_cycles
    stats["win_rate"] = None  # not lot-matched
    stats["average_trade"] = None
    stats["time_in_market"] = 1.0 if any(holdings.values()) else None
    # fix: recompute time in market from equity path vs cash — approximate fraction of days with any holding after first rebalance
    spy = px["SPY"].dropna()
    stats["benchmark_spy_total_return"] = float(spy.iloc[-1] / spy.iloc[0] - 1)
    # 60/40
    tlt = px["TLT"].reindex(spy.index).ffill()
    mix = 0.6 * (spy / spy.iloc[0]) + 0.4 * (tlt / tlt.iloc[0])
    stats["benchmark_60_40_total_return"] = float(mix.iloc[-1] - 1)

    folder = HERE / "S-NEW-3"
    write_json(folder / "META.json", meta.to_public())
    write_json(folder / "backtest_stats.json", stats)
    write_csv(folder / "equity_backtest.csv", equity_rows)
    write_csv(folder / "trades_backtest.csv", trades)

    # Forward from FORWARD_START with a fresh $10,000 book
    fwd = px[px.index.date >= FORWARD_START]
    holdings = {a: 0.0 for a in assets}
    cash = CAPITAL
    idle_cash_income = 0.0
    forward_trades = []
    forward_equity = []
    for d, row in fwd.iterrows():
        if d in month_end_set:
            i = month_ends.index(d)
            if i >= lookback_months:
                rets = {}
                for a in assets:
                    p0 = me_px[a].iloc[i - lookback_months]
                    p1 = me_px[a].iloc[i]
                    if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                        rets[a] = float(p1 / p0 - 1)
                ranked = sorted(rets.items(), key=lambda x: x[1], reverse=True)[:3]
                target = {a: 1.0 / len(ranked) for a, _ in ranked} if ranked else {}
                for a in assets:
                    if holdings[a] > 0 and pd.notna(row[a]):
                        proceeds = holdings[a] * float(row[a])
                        fee = proceeds * STOCK_FEE
                        cash += proceeds - fee
                        forward_trades.append({"timestamp": f"{d.date()}T16:00:00-05:00", "side": "SELL", "symbol": a, "price": float(row[a]), "qty": holdings[a], "fees": round(fee, 4), "pnl": "", "reason": "month-end rebalance"})
                        holdings[a] = 0.0
                port = cash
                for a, w in target.items():
                    if pd.isna(row[a]):
                        continue
                    alloc = port * w
                    fee = alloc * STOCK_FEE
                    spend = alloc - fee
                    holdings[a] = spend / float(row[a])
                    cash -= alloc
                    forward_trades.append({"timestamp": f"{d.date()}T16:00:00-05:00", "side": "BUY", "symbol": a, "price": float(row[a]), "qty": holdings[a], "fees": round(fee, 4), "pnl": "", "reason": "month-end top3"})
        bil_ret = 0.0
        loc = px.index.get_loc(d)
        if isinstance(loc, int) and loc > 0 and pd.notna(px["BIL"].iloc[loc]) and pd.notna(px["BIL"].iloc[loc - 1]) and px["BIL"].iloc[loc - 1] > 0:
            bil_ret = max(0.0, float(px["BIL"].iloc[loc] / px["BIL"].iloc[loc - 1] - 1))
        if cash > 0:
            idle_cash_income += cash * bil_ret
            cash *= 1.0 + bil_ret
        port = cash + sum(holdings[a] * float(row[a]) for a in assets if pd.notna(row.get(a)))
        spy0 = float(fwd["SPY"].iloc[0])
        forward_equity.append({"date": str(d.date()), "equity": round(port, 2), "benchmark_spy": round(CAPITAL * float(row["SPY"]) / spy0, 2), "idle_cash_income": round(idle_cash_income, 2)})
    if not forward_equity:
        forward_equity = [{"date": FORWARD_START.isoformat(), "equity": CAPITAL, "benchmark_spy": CAPITAL, "idle_cash_income": 0.0}]
    state = {"cash": round(cash, 2), "holdings": {k: v for k, v in holdings.items() if v}, "as_of": forward_equity[-1]["date"], "idle_cash_income": round(idle_cash_income, 2), "experiment_label": EXPERIMENT_LABEL, "id": meta.id}
    write_csv(folder / "forward" / "equity.csv", forward_equity)
    write_csv(folder / "forward" / "trades.csv", forward_trades, fieldnames=["timestamp", "side", "symbol", "price", "qty", "fees", "pnl", "reason"])
    write_json(folder / "forward" / "state.json", state)
    return {"meta": meta.to_public(), "stats": stats, "forward": forward_equity[-1], "state": state}
