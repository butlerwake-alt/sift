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
    classify_status,
    load_yahoo,
    load_yahoo_ohlc,
    load_yahoo_ohlc_panel,
    max_drawdown,
    summarize_backtest,
    turnover_from_trades,
    write_csv,
    write_forward_ledger,
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


def run_s_new_4() -> dict:
    """ETF Trend & Cash — Faber-style 10-month SMA sleeves. Frozen before inspecting results."""
    meta = StrategyMeta(
        id="S-NEW-4",
        name="ETF Trend & Cash",
        category="Stock Strategy",
        source="https://ssrn.com/abstract=962461",
        why="Tests whether a published 10-month SMA trend filter on five liquid ETFs reduces drawdown versus a passive equal-weight of the same sleeves. Rules frozen from Faber (2007) before looking at results; no parameter search.",
        why_fail="Trend filters lag sharp reversals; five-ETF universe is today's liquid proxies (survivorship); month-end signals with next-open fills and 1.5× costs can erase thin edges; cash proxy (BIL) differs from T-bills in the paper.",
        rules=[
            "Universe (five equal sleeves): SPY, EFA, IEF, VNQ, DBC.",
            "Signal series: dividend- and split-adjusted monthly closes (Yahoo Finance auto_adjust).",
            "At each month-end close, compare each ETF’s adjusted close to its 10-month simple moving average, including the just-completed month.",
            "Allocate 20% to each ETF above its 10-month SMA; hold remaining weight in cash (BIL yield).",
            "Execute the rebalance at the next regular session open using tradable opens under the same corporate-action adjustment.",
            f"Base cost: {STOCK_FEE*100:.3f}% fee+slippage per side on turnover (1.5× desk 0.05%). Also report doubled-cost results.",
            "Benchmark: same five ETFs, always 20% each, rebalanced on the same month-end→next-open schedule with the same cost model.",
            "Long-only, unleveraged, paper only. No broker credentials.",
        ],
        benchmarks=[
            "Passive 5-ETF equal weight (same schedule)",
            "Doubled-cost trend variant (comparison)",
        ],
        fee_per_side=STOCK_FEE,
    )

    assets = ["SPY", "EFA", "IEF", "VNQ", "DBC"]
    data_source = "Yahoo Finance (yfinance) adjusted OHLC, auto_adjust=True"
    panel = load_yahoo_ohlc_panel(assets + ["BIL"], "2006-01-01")
    # Align on intersection of trading days with required columns
    closes = pd.DataFrame({a: panel[a]["Close"] for a in assets}).dropna(how="any").sort_index()
    opens = pd.DataFrame({a: panel[a]["Open"] for a in assets}).reindex(closes.index)
    bil_close = panel["BIL"]["Close"].reindex(closes.index).ffill()
    cash_y = bil_daily_yield(bil_close)

    # Monthly last trading day closes for SMA signal
    month_ends = list(closes.groupby([closes.index.year, closes.index.month]).tail(1).index)
    me_close = closes.loc[month_ends]
    sma10 = me_close.rolling(10, min_periods=10).mean()

    # Map: month-end decision date → target weights; fill at next session open after that date
    decisions: dict[pd.Timestamp, dict[str, float]] = {}
    for i, me in enumerate(month_ends):
        if i < 9:  # need 10 months including current → index >= 9
            continue
        if sma10.loc[me].isna().any():
            continue
        target = {}
        for a in assets:
            if float(me_close.loc[me, a]) > float(sma10.loc[me, a]):
                target[a] = 0.20
        decisions[me] = target  # may be empty → 100% cash

    dates = list(closes.index)
    date_to_i = {d: i for i, d in enumerate(dates)}

    def next_open_day(after: pd.Timestamp) -> pd.Timestamp | None:
        i = date_to_i.get(after)
        if i is None:
            # find first date > after
            for d in dates:
                if d > after:
                    return d
            return None
        if i + 1 < len(dates):
            return dates[i + 1]
        return None

    # Pending fills: exec_date → target weights decided at prior month-end
    pending: dict[pd.Timestamp, dict[str, float]] = {}
    for me, tgt in decisions.items():
        nxt = next_open_day(me)
        if nxt is not None:
            pending[nxt] = tgt

    warm_start = month_ends[9] if len(month_ends) > 9 else (month_ends[0] if month_ends else None)
    # Chronological holdout after warm-up: from first valid signal onward through day before forward start
    holdout_start = next_open_day(warm_start) if warm_start is not None else None

    def simulate(fee: float, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None):
        holdings = {a: 0.0 for a in assets}
        cash = CAPITAL
        equity_rows = []
        trades = []
        bench_holdings = {a: 0.0 for a in assets}
        bench_cash = CAPITAL
        bench_rows = []
        idle_income = 0.0
        data_failures = []
        last_signal = "awaiting"
        last_decision = None
        skipped = 0

        use_dates = dates
        if start is not None:
            use_dates = [d for d in use_dates if d >= start]
        if end is not None:
            use_dates = [d for d in use_dates if d <= end]
        if not use_dates:
            return {
                "equity": [],
                "trades": [],
                "bench": [],
                "idle_income": 0.0,
                "data_failures": ["No overlapping price history in window"],
                "last_signal": "awaiting",
                "last_decision": None,
                "skipped": 0,
                "holdings": holdings,
                "cash": cash,
            }

        # Seed passive benchmark at first open of window (equal 20%)
        d0 = use_dates[0]
        missing0 = [a for a in assets if pd.isna(opens.loc[d0, a]) or float(opens.loc[d0, a]) <= 0]
        if missing0:
            data_failures.append(f"{d0.date()}: missing opens {missing0} at window start")
        else:
            for a in assets:
                px = float(opens.loc[d0, a])
                alloc = CAPITAL * 0.20
                fee_amt = alloc * fee
                spend = alloc - fee_amt
                bench_holdings[a] = spend / px
                bench_cash -= alloc
                # trend book starts in cash until first rebalance fill
            trades.append(
                {
                    "date": str(d0.date()),
                    "side": "SEED_BENCH",
                    "symbol": "MULTI",
                    "price": 0.0,
                    "shares": 0.0,
                    "fees": round(CAPITAL * 0.20 * fee * 5, 4),
                    "pnl": None,
                    "reason": "passive 20% seed at window open (benchmark accounting)",
                }
            )

        for d in use_dates:
            # Execute pending rebalance at open
            if d in pending:
                tgt = pending[d]
                last_signal = "trend_on" if tgt else "none"
                last_decision = {
                    "decision_for": str(d.date()),
                    "targets": tgt,
                    "cash_weight": round(1.0 - sum(tgt.values()), 4),
                    "reason": "month-end SMA10 vs close; fill next open",
                }
                missing = [a for a in assets if pd.isna(opens.loc[d, a]) or float(opens.loc[d, a]) <= 0]
                if missing:
                    data_failures.append(f"{d.date()}: missing open prices {missing}; skipped rebalance")
                    skipped += 1
                else:
                    # Liquidate trend book to cash at open
                    for a in assets:
                        if holdings[a] > 0:
                            px = float(opens.loc[d, a])
                            proceeds = holdings[a] * px
                            fee_amt = proceeds * fee
                            cash += proceeds - fee_amt
                            trades.append(
                                {
                                    "date": str(d.date()),
                                    "side": "SELL",
                                    "symbol": a,
                                    "price": px,
                                    "shares": holdings[a],
                                    "fees": round(fee_amt, 4),
                                    "pnl": None,
                                    "reason": "trend rebalance exit at next open",
                                }
                            )
                            holdings[a] = 0.0
                    port = cash
                    for a, w in tgt.items():
                        px = float(opens.loc[d, a])
                        alloc = port * w
                        fee_amt = alloc * fee
                        spend = alloc - fee_amt
                        holdings[a] = spend / px
                        cash -= alloc
                        trades.append(
                            {
                                "date": str(d.date()),
                                "side": "BUY",
                                "symbol": a,
                                "price": px,
                                "shares": holdings[a],
                                "fees": round(fee_amt, 4),
                                "pnl": None,
                                "reason": "trend sleeve on (close > 10m SMA)",
                            }
                        )
                    # Passive benchmark rebalance to 20% each at same open
                    b_port = bench_cash + sum(
                        bench_holdings[a] * float(opens.loc[d, a]) for a in assets
                    )
                    for a in assets:
                        if bench_holdings[a] > 0:
                            px = float(opens.loc[d, a])
                            proceeds = bench_holdings[a] * px
                            fee_amt = proceeds * fee
                            bench_cash += proceeds - fee_amt
                            bench_holdings[a] = 0.0
                    for a in assets:
                        px = float(opens.loc[d, a])
                        alloc = b_port * 0.20
                        fee_amt = alloc * fee
                        spend = alloc - fee_amt
                        bench_holdings[a] = spend / px
                        bench_cash -= alloc

            # Daily mark at close + idle cash yield
            y = float(cash_y.get(d, 0.0))
            if cash > 0:
                earned = cash * y
                idle_income += earned
                cash *= 1.0 + y
            if bench_cash > 0:
                bench_cash *= 1.0 + y
            row_ok = True
            for a in assets:
                if pd.isna(closes.loc[d, a]):
                    row_ok = False
                    break
            if not row_ok:
                data_failures.append(f"{d.date()}: missing close; preserved prior mark skipped")
                skipped += 1
                continue
            port = cash + sum(holdings[a] * float(closes.loc[d, a]) for a in assets)
            b_port = bench_cash + sum(bench_holdings[a] * float(closes.loc[d, a]) for a in assets)
            equity_rows.append({"date": str(d.date()), "equity": round(port, 2)})
            bench_rows.append({"date": str(d.date()), "equity": round(b_port, 2)})

        return {
            "equity": equity_rows,
            "trades": trades,
            "bench": bench_rows,
            "idle_income": idle_income,
            "data_failures": data_failures,
            "last_signal": last_signal,
            "last_decision": last_decision,
            "skipped": skipped,
            "holdings": holdings,
            "cash": cash,
            "bench_holdings": bench_holdings,
            "bench_cash": bench_cash,
        }

    if holdout_start is None or len(closes) < 250:
        folder = HERE / "S-NEW-4"
        stats = {
            "label": "Historical backtest, not forward results",
            "awaiting_verified_historical_data": True,
            "reason": "Insufficient overlapping adjusted OHLC history for a 10-month SMA warm-up and chronological holdout.",
            "data_source": data_source,
            "cagr": None,
            "sharpe": None,
            "deflated_sharpe": None,
            "max_drawdown": None,
            "trades": None,
            "win_rate": None,
            "average_trade": None,
            "time_in_market": None,
            "over_10pct_dd": None,
            "crash_periods": {},
            "start": None,
            "end": None,
        }
        write_json(folder / "META.json", meta.to_public())
        write_json(folder / "backtest_stats.json", stats)
        write_forward_ledger(
            folder,
            [{"date": FORWARD_START.isoformat(), "equity": CAPITAL, "benchmark_passive5": CAPITAL, "idle_cash_income": 0.0}],
            [],
            {
                "cash": CAPITAL,
                "holdings": {},
                "as_of": None,
                "idle_cash_income": 0.0,
                "exposure": 0.0,
                "last_signal": "awaiting",
                "last_decision": None,
                "status": "Awaiting first mark",
                "data_failure": stats["reason"],
                "experiment_label": EXPERIMENT_LABEL,
                "id": meta.id,
            },
        )
        return {"meta": meta.to_public(), "stats": stats, "forward": {"equity": CAPITAL}, "state": {}}

    # Holdout window: first executable signal through day before FORWARD_START (or last bar)
    holdout_end_candidates = [d for d in dates if d.date() < FORWARD_START]
    holdout_end = holdout_end_candidates[-1] if holdout_end_candidates else dates[-1]
    base = simulate(STOCK_FEE, start=holdout_start, end=holdout_end)
    doubled = simulate(STOCK_FEE * 2.0, start=holdout_start, end=holdout_end)

    eq_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in base["equity"]})
    bench_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in base["bench"]})
    closed = [{"pnl": 0.0} for t in base["trades"] if t["side"] == "SELL"]
    stats = summarize_backtest(eq_s, closed, periods_per_year=252) if len(eq_s) >= 2 else {
        "label": "Historical backtest, not forward results",
        "awaiting_verified_historical_data": True,
        "reason": "Holdout equity path too short after warm-up.",
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
        stats["warmup_months"] = 10
        stats["holdout_start"] = str(holdout_start.date())
        stats["holdout_end"] = str(holdout_end.date())
        stats["trades"] = sum(1 for t in base["trades"] if t["side"] in ("BUY", "SELL"))
        stats["fill_count"] = stats["trades"]
        raw_to = turnover_from_trades(
            [{"price": t["price"], "qty": t["shares"]} for t in base["trades"] if t["side"] in ("BUY", "SELL")]
        )
        years = max(len(eq_s) / 252.0, 1e-9)
        stats["turnover"] = raw_to / years
        stats["turnover_total"] = raw_to
        stats["win_rate"] = None
        stats["average_trade"] = None
        # time in market not lot-tracked daily in this sleeve model
        stats["time_in_market"] = None
        if len(bench_s) >= 2:
            stats["benchmark_passive5_total_return"] = float(bench_s.iloc[-1] / CAPITAL - 1)
            stats["benchmark_passive5_max_drawdown"] = max_drawdown(bench_s)
            stats["benchmark_gap"] = float(eq_s.iloc[-1] / CAPITAL - bench_s.iloc[-1] / CAPITAL)
            # Both max_drawdown values are ≤ 0. Positive drawdown_reduction ⇒ trend milder than passive.
            stats["drawdown_reduction"] = float(
                max_drawdown(eq_s) - max_drawdown(bench_s)
            )
            # Positive return_given_up ⇒ trend lagged the passive sleeve book.
            stats["return_given_up"] = float(
                (bench_s.iloc[-1] / CAPITAL - 1) - (eq_s.iloc[-1] / CAPITAL - 1)
            )
        dbl_s = pd.Series({pd.Timestamp(r["date"]): r["equity"] for r in doubled["equity"]})
        if len(dbl_s) >= 2:
            stats["doubled_cost_total_return"] = float(dbl_s.iloc[-1] / CAPITAL - 1)
            stats["doubled_cost_max_drawdown"] = max_drawdown(dbl_s)
            stats["doubled_cost_fill_count"] = sum(
                1 for t in doubled["trades"] if t["side"] in ("BUY", "SELL")
            )
        stats["vs_published_research"] = (
            "Faber (2007, SSRN 962461) used monthly trend vs 10-month SMA on asset-class proxies "
            "and moved to T-bills when below the average. This paper test uses liquid ETF sleeves "
            "(SPY/EFA/IEF/VNQ/DBC), Yahoo dividend-adjusted prices, next-session-open fills after "
            "month-end signals (no same-close execution), BIL as the cash proxy, and 1.5× desk "
            "costs. Equal 20% sleeve caps match the five-asset equal-risk framing; the original "
            "write-up also discusses absolute momentum with cash, which we keep."
        )

    folder = HERE / "S-NEW-4"
    write_json(folder / "META.json", meta.to_public())
    write_json(folder / "backtest_stats.json", stats)
    write_csv(folder / "equity_backtest.csv", base["equity"])
    write_csv(folder / "trades_backtest.csv", base["trades"])
    write_csv(folder / "comparisons" / "passive5_equity.csv", base["bench"])
    write_csv(folder / "comparisons" / "doubled_cost_equity.csv", doubled["equity"])

    # Forward ledger from FORWARD_START (separate from holdout)
    fwd_start = None
    for d in dates:
        if d.date() >= FORWARD_START:
            fwd_start = d
            break
    if fwd_start is None:
        fwd_start = dates[-1]

    fwd = simulate(STOCK_FEE, start=fwd_start, end=dates[-1])
    # Convert forward trades to ledger schema
    forward_trades = []
    for t in fwd["trades"]:
        if t["side"] not in ("BUY", "SELL"):
            continue
        forward_trades.append(
            {
                "timestamp": f"{t['date']}T09:30:00-05:00",
                "side": t["side"],
                "symbol": t["symbol"],
                "price": t["price"],
                "qty": t["shares"],
                "fees": t["fees"],
                "pnl": "" if t.get("pnl") is None else t["pnl"],
                "reason": t["reason"],
            }
        )
    forward_equity = []
    for i, r in enumerate(fwd["equity"]):
        b = fwd["bench"][i]["equity"] if i < len(fwd["bench"]) else CAPITAL
        forward_equity.append(
            {
                "date": r["date"],
                "equity": r["equity"],
                "benchmark_passive5": b,
                "idle_cash_income": round(fwd["idle_income"], 2),
            }
        )
    if not forward_equity:
        forward_equity = [
            {
                "date": FORWARD_START.isoformat(),
                "equity": CAPITAL,
                "benchmark_passive5": CAPITAL,
                "idle_cash_income": 0.0,
            }
        ]

    # Exposure from last mark
    last_date = pd.Timestamp(forward_equity[-1]["date"])
    port = forward_equity[-1]["equity"] or CAPITAL
    invested = 0.0
    holdings_out = {}
    if last_date in closes.index:
        for a, qty in fwd["holdings"].items():
            if qty and not pd.isna(closes.loc[last_date, a]):
                val = qty * float(closes.loc[last_date, a])
                invested += val
                holdings_out[a] = qty
    exposure = invested / port if port else 0.0
    data_failure = "; ".join(fwd["data_failures"][-3:]) if fwd["data_failures"] else None
    status = classify_status(
        as_of=forward_equity[-1]["date"],
        exposure=exposure,
        last_signal=fwd["last_signal"],
        data_failure=data_failure if fwd["skipped"] and not holdings_out and fwd["cash"] >= CAPITAL * 0.99 and len(fwd["equity"]) <= 1 else (
            data_failure if (data_failure and "missing" in (data_failure or "") and exposure < 0.005 and fwd["last_signal"] == "awaiting") else None
        ),
        category="Stock Strategy",
    )
    # Prefer explicit cash/no-signal when we have marks
    if status == "Invested" and exposure < 0.005:
        status = "In cash" if fwd["last_signal"] != "none" else "No signal"
    if fwd["last_signal"] == "none" and exposure < 0.005:
        status = "No signal"
    if fwd["last_signal"] == "awaiting" and exposure < 0.005 and len(forward_trades) == 0:
        # Day-1 before first month-end decision
        status = "In cash" if forward_equity[-1]["date"] else "Awaiting first mark"

    last_decision = fwd["last_decision"]
    if last_decision is None and exposure < 0.005:
        last_decision = {
            "action": "hold_cash",
            "note": "Awaiting first month-end SMA signal" if fwd["last_signal"] == "awaiting" else "No sleeves above 10-month SMA",
            "cash": round(fwd["cash"], 2),
        }

    state = {
        "cash": round(fwd["cash"], 2),
        "holdings": {k: v for k, v in holdings_out.items() if v},
        "as_of": forward_equity[-1]["date"],
        "idle_cash_income": round(fwd["idle_income"], 2),
        "exposure": round(exposure, 4),
        "last_signal": fwd["last_signal"],
        "last_decision": last_decision,
        "status": status,
        "data_failures": fwd["data_failures"][-10:],
        "data_source": data_source,
        "experiment_label": EXPERIMENT_LABEL,
        "id": meta.id,
    }
    write_forward_ledger(folder, forward_equity, forward_trades, state)
    return {"meta": meta.to_public(), "stats": stats, "forward": forward_equity[-1], "state": state}
