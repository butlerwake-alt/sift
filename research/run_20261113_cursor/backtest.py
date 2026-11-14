"""NEW EXPERIMENT dated 2026-11-13 (America/New_York) — historical backtests of publicly claimed crypto strategies.
Paper/backtest only. No exchange keys, no real orders, no leverage, long-only.
Banned: volatility-sizing, volatility-brake, leverage-momentum variants.
Rules were frozen in the STRATEGY RULES block below BEFORE any results were inspected.

Data: Yahoo Finance daily (BTC-USD, ETH-USD, SOL-USD); alternative.me Fear & Greed; public funding histories (see data/manifest.json).
Fills: signal at close of bar t fills at OPEN of bar t+1 (headline). Sensitivity: fill at signal close.
Fees: 0.10% per side on every traded dollar. Idle cash earns 0.
Windows: full available history per strategy, and Nov 1, 2021 → last complete bar.
Sharpe: raw daily return × √365.
VERDICT (written before the run):
  Promising = Sharpe > buy-and-hold in BOTH windows AND full-window max drawdown shallower than buy-and-hold.
  Failed    = Sharpe < buy-and-hold in BOTH windows.
  Mixed     = everything else.
  10% drawdown limit: PASS only if full-window max drawdown (daily closes) ≥ −10%.
"""
from __future__ import annotations
import json, os
import numpy as np
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))
END = pd.Timestamp("2026-11-12")          # last complete UTC day in the Yahoo snapshot
RECENT = pd.Timestamp("2021-11-01")       # user-requested recent window
FEE = 0.001
CAP = 10000.0

def load_ohlc(t):
    d = pd.read_csv(f"data/{t}.csv", index_col=0, parse_dates=True)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d[d.index <= END]

BTC, ETH, SOL = (load_ohlc(t) for t in ["BTC-USD", "ETH-USD", "SOL-USD"])
PX = {"BTC": BTC, "ETH": ETH, "SOL": SOL}

FG = pd.read_csv("data/fear_greed.csv", index_col=0, parse_dates=True)["value"].astype(float)
FG = FG[~FG.index.duplicated(keep="last")].sort_index()
FG = FG[FG.index <= END]

def load_funding(path):
    d = pd.read_csv(path)
    d["fundingTime"] = pd.to_datetime(d["fundingTime"], utc=True).dt.tz_convert(None)
    d = d.drop_duplicates("fundingTime").sort_values("fundingTime")
    # daily last funding print
    daily = d.set_index("fundingTime")["fundingRate"].resample("1D").last().dropna()
    # also 3-day mean of 8h prints → map to calendar day via trailing mean of daily last
    # better: resample 8h series to daily mean
    s = d.set_index("fundingTime")["fundingRate"]
    daily_mean = s.resample("1D").mean()
    trail3 = daily_mean.rolling(3, min_periods=1).mean()
    return trail3[trail3.index <= END]

FUND_BTC = load_funding("data/funding_BTCUSDT.csv")

# ---------- indicators ----------
def rsi(c, n):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

def adx(d, n=2):
    """Wilder ADX with period n (n=2 as claimed by the Reddit source)."""
    h, l, c = d["High"], d["Low"], d["Close"]
    up = h.diff(); down = -l.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = pd.Series(tr, index=d.index).ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=d.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=d.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    return dx.ewm(alpha=1 / n, adjust=False).mean()

def atr(d, n):
    pc = d["Close"].shift()
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()

def state_machine(entry, exit_):
    pos = np.zeros(len(entry)); p = 0
    for i, (e, x) in enumerate(zip(entry.fillna(False).values, exit_.fillna(False).values)):
        if p == 0 and bool(e): p = 1
        elif p == 1 and bool(x): p = 0
        pos[i] = p
    return pd.Series(pos, index=entry.index)

def month_end_flags(idx):
    s = pd.Series(idx, index=idx)
    return s.groupby([idx.year, idx.month]).transform("max") == s

# =============================================================================
# STRATEGY RULES (frozen before the run — do not tune after seeing results)
# =============================================================================
def s_rsi_adx_btc():
    """Reddit r/algotrading u/draderdim (2025-06-28): claimed beat HODL on BTC/ETH.
    Entry: Close>SMA50 AND Close>EMA7 AND RSI(2)>ADX(2). Exit: RSI(2)<ADX(2)."""
    d = BTC; c = d["Close"]
    ent = (c > c.rolling(50).mean()) & (c > c.ewm(span=7, adjust=False).mean()) & (rsi(c, 2) > adx(d, 2))
    ex = rsi(c, 2) < adx(d, 2)
    return {"BTC": state_machine(ent, ex)}

def s_double7_btc():
    """Larry Connors Double 7s (QuantifiedStrategies / Alvarez); claimed on X for liquid markets / BTC tests.
    Entry: Close>SMA200 and Close is lowest close of last 7. Exit: Close is highest close of last 7."""
    c = BTC["Close"]
    lo7 = c.rolling(7).min(); hi7 = c.rolling(7).max()
    ent = (c > c.rolling(200).mean()) & (c <= lo7)
    ex = c >= hi7
    return {"BTC": state_machine(ent, ex)}

def s_keltner_trio():
    """Keel / CoinQuant Keltner breakout (long only): close > EMA20 + 2*ATR(20); exit close <= EMA20.
    Each of BTC/ETH/SOL gets up to 1/3 weight independently."""
    out = {}
    for name, d in PX.items():
        ema = d["Close"].ewm(span=20, adjust=False).mean()
        upper = ema + 2 * atr(d, 20)
        ent = d["Close"] > upper
        ex = d["Close"] <= ema
        out[name] = state_machine(ent, ex) / 3.0
    return out

def s_weekly_rsi_accum_btc():
    """24crypto.news weekly RSI+SMA50 accumulation window.
    Enter when weekly RSI(14) < 30; exit when weekly close > weekly SMA(50)."""
    c = BTC["Close"]
    wk = c.resample("W-SUN").last()
    wrsi = rsi(wk, 14); wsma = wk.rolling(50).mean()
    st = state_machine(wrsi < 30, wk > wsma)
    return {"BTC": st.reindex(c.index).ffill().fillna(0)}

def s_rsi30_50_eth():
    """Classic RSI 30/50 claim (altrady on X, Coinrule academy): buy RSI(14)<30, sell RSI(14)>=50. ETH daily."""
    c = ETH["Close"]
    r = rsi(c, 14)
    return {"ETH": state_machine(r < 30, r >= 50)}

def s_fear_greed_btc():
    """Binary form of the Fear & Greed contrarian idea (Bitcoin Magazine / calculator sites).
    Enter when F&G ≤ 25; exit when F&G ≥ 75. Hold between."""
    idx = BTC.index.intersection(FG.index)
    g = FG.reindex(idx)
    ent = g <= 25; ex = g >= 75
    return {"BTC": state_machine(ent, ex).reindex(BTC.index).fillna(0)}

def s_dual_mom_4w():
    """FinzData: each week hold whichever of BTC/ETH/SOL has the higher 28-day return; cash if that return ≤ 0."""
    idx = BTC.index.intersection(ETH.index).intersection(SOL.index)
    px = pd.DataFrame({a: PX[a]["Close"].reindex(idx) for a in ["BTC", "ETH", "SOL"]})
    r28 = px / px.shift(28) - 1
    # Sunday week-end decision (crypto trades weekends; use calendar week-end)
    we = px.groupby([px.index.year, px.index.isocalendar().week]).transform("last")
    # mark week-end rows: last bar of each ISO week
    is_we = px.index.to_series().groupby([px.index.year, px.index.isocalendar().week]).transform("max") == px.index.to_series()
    W = pd.DataFrame(0.0, index=idx, columns=["BTC", "ETH", "SOL"])
    for t in idx[is_we.values]:
        row = r28.loc[t]
        if row.isna().all(): continue
        best = row.idxmax()
        if pd.notna(row[best]) and row[best] > 0:
            W.loc[t, best] = 1.0
    W = W.ffill().fillna(0)
    return {a: W[a] for a in W.columns}

def s_funding_contrarian_btc():
    """Earnflow-style funding filter as a binary spot timing rule (long only, no leverage):
    Long while 3-day average funding ≤ 0; cash when 3-day average funding > +0.01% (0.0001)."""
    f = FUND_BTC.reindex(BTC.index).ffill()
    ent = f <= 0; ex = f > 0.0001
    # only after funding data exists
    valid = f.notna()
    ent = ent & valid; ex = ex | ~valid
    return {"BTC": state_machine(ent, ex)}

def s_mayer_btc():
    """Trace Mayer / CoinDesk: accumulate while Mayer Multiple (Close/SMA200) < 2.4; flat when ≥ 2.4."""
    c = BTC["Close"]; mm = c / c.rolling(200).mean()
    return {"BTC": (mm < 2.4).astype(float).where(mm.notna(), 0.0)}

def s_abs_dual_mom_monthly():
    """Becoming Crypto Whale / Saral absolute dual-momentum style on BTC/ETH/SOL:
    At month-end hold the asset with the highest 90-day return if that return > 0; else cash."""
    idx = BTC.index.intersection(ETH.index).intersection(SOL.index)
    px = pd.DataFrame({a: PX[a]["Close"].reindex(idx) for a in ["BTC", "ETH", "SOL"]})
    r90 = px / px.shift(90) - 1
    me = month_end_flags(idx)
    W = pd.DataFrame(0.0, index=idx, columns=["BTC", "ETH", "SOL"])
    for t in idx[me.values]:
        row = r90.loc[t]
        if row.isna().all(): continue
        best = row.idxmax()
        if pd.notna(row[best]) and row[best] > 0:
            W.loc[t, best] = 1.0
    W = W.ffill().fillna(0)
    return {a: W[a] for a in W.columns}

STRATS = {
    "rsi_adx_btc": dict(fn=s_rsi_adx_btc, universe=["BTC"], label="BTC"),
    "double7_btc": dict(fn=s_double7_btc, universe=["BTC"], label="BTC"),
    "keltner_trio": dict(fn=s_keltner_trio, universe=["BTC", "ETH", "SOL"], label="BTC/ETH/SOL"),
    "weekly_rsi_accum_btc": dict(fn=s_weekly_rsi_accum_btc, universe=["BTC"], label="BTC"),
    "rsi30_50_eth": dict(fn=s_rsi30_50_eth, universe=["ETH"], label="ETH"),
    "fear_greed_btc": dict(fn=s_fear_greed_btc, universe=["BTC"], label="BTC"),
    "dual_mom_4w": dict(fn=s_dual_mom_4w, universe=["BTC", "ETH", "SOL"], label="BTC/ETH/SOL"),
    "funding_contrarian_btc": dict(fn=s_funding_contrarian_btc, universe=["BTC"], label="BTC"),
    "mayer_lt_2p4_btc": dict(fn=s_mayer_btc, universe=["BTC"], label="BTC"),
    "abs_dual_mom_monthly": dict(fn=s_abs_dual_mom_monthly, universe=["BTC", "ETH", "SOL"], label="BTC/ETH/SOL"),
}

# ---------- simulator (same economics as run_20261110) ----------
def simulate(weights, start, fee, mode):
    assets = list(weights)
    idx = None
    for a in assets:
        ix = PX[a].index
        idx = ix if idx is None else idx.intersection(ix)
    idx = idx[idx >= start]
    W = pd.DataFrame({a: weights[a].reindex(idx).fillna(0) for a in assets})
    O = pd.DataFrame({a: PX[a]["Open"].reindex(idx) for a in assets})
    C = pd.DataFrame({a: PX[a]["Close"].reindex(idx) for a in assets})
    eq = CAP; held = {a: 0.0 for a in assets}
    out = [eq]; trades = []; open_tr = {}
    Wv, Ov, Cv = W.values, O.values, C.values

    def rebalance(i, price_row, target):
        nonlocal eq
        turnover = sum(abs(target[j] - held[a]) for j, a in enumerate(assets))
        eq_before = eq
        eq *= (1 - fee * turnover)
        for j, a in enumerate(assets):
            if held[a] == 0 and target[j] > 0:
                open_tr[a] = (idx[i], eq_before, price_row[j])
            if held[a] > 0 and target[j] == 0 and a in open_tr:
                d0, e0, p0 = open_tr.pop(a)
                trades.append((a, str(d0.date()), str(idx[i].date()), (price_row[j] / p0) * (1 - fee) ** 2 - 1))
            held[a] = target[j]

    if mode == "close":
        rebalance(0, Cv[0], Wv[0])
    for i in range(1, len(idx)):
        if mode == "open":
            r_on = sum(held[a] * (Ov[i][j] / Cv[i - 1][j] - 1) for j, a in enumerate(assets))
            eq *= 1 + r_on
            rebalance(i, Ov[i], Wv[i - 1])
            r_id = sum(held[a] * (Cv[i][j] / Ov[i][j] - 1) for j, a in enumerate(assets))
            eq *= 1 + r_id
        else:
            r = sum(held[a] * (Cv[i][j] / Cv[i - 1][j] - 1) for j, a in enumerate(assets))
            eq *= 1 + r
            rebalance(i, Cv[i], Wv[i])
        out.append(eq)
    for a, (d0, e0, p0) in open_tr.items():
        j = assets.index(a)
        trades.append((a, str(d0.date()), "open", Cv[-1][j] / p0 * (1 - fee) - 1))
    exposure = (W.shift(1).fillna(0).sum(axis=1) > 0).mean() if mode == "open" else (W.sum(axis=1) > 0).mean()
    return pd.Series(out, index=idx), trades, float(exposure)

def buy_hold(universe, start, fee):
    """Equal-weight buy-and-hold across universe assets present at start."""
    idx = None
    for a in universe:
        ix = PX[a].index
        idx = ix if idx is None else idx.intersection(ix)
    idx = idx[idx >= start]
    n = len(universe)
    # buy at first open, hold to close path with equal weights, one fee on entry
    O0 = {a: PX[a]["Open"].reindex(idx).iloc[0] for a in universe}
    C = pd.DataFrame({a: PX[a]["Close"].reindex(idx) for a in universe})
    # equal dollar units from first open
    units = {a: (CAP / n) * (1 - fee) / O0[a] for a in universe}
    eq = sum(units[a] * C[a] for a in universe)
    return eq

def metrics(eq, ann=365):
    r = eq.pct_change().dropna()
    yrs = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    dd = (eq / eq.cummax() - 1).min()
    dd = min(dd, eq.iloc[0] / CAP - 1, 0)
    return {
        "total_return_pct": round((eq.iloc[-1] / CAP - 1) * 100, 2),
        "cagr_pct": round(((eq.iloc[-1] / CAP) ** (1 / yrs) - 1) * 100, 2),
        "max_dd_pct": round(dd * 100, 2),
        "sharpe": round(r.mean() / r.std() * np.sqrt(ann), 2) if r.std() > 0 else 0.0,
        "final": round(float(eq.iloc[-1]), 2),
    }

# Full-history start per strategy: first date with enough data among its universe
STARTS = {
    "rsi_adx_btc": pd.Timestamp("2015-01-01"),
    "double7_btc": pd.Timestamp("2015-01-01"),
    "keltner_trio": pd.Timestamp("2020-04-10"),  # SOL listing
    "weekly_rsi_accum_btc": pd.Timestamp("2015-01-01"),
    "rsi30_50_eth": pd.Timestamp("2018-01-01"),
    "fear_greed_btc": pd.Timestamp("2018-02-01"),
    "dual_mom_4w": pd.Timestamp("2020-04-10"),
    "funding_contrarian_btc": pd.Timestamp("2020-01-01"),
    "mayer_lt_2p4_btc": pd.Timestamp("2015-01-01"),
    "abs_dual_mom_monthly": pd.Timestamp("2020-04-10"),
}

results = {}; curves = {}
os.makedirs("results", exist_ok=True)
for key, S in STRATS.items():
    w = S["fn"](); univ = S["universe"]
    start = STARTS[key]
    res = {"market": S["label"], "fee_per_side_pct": FEE * 100, "windows": {}}
    for wname, ws in [("full", start), ("recent", RECENT)]:
        # ensure recent window does not start before asset exists
        ws2 = max(ws, start)
        row = {}
        for mode in ["open", "close"]:
            eq, tr, expo = simulate(w, ws2, FEE, mode)
            m = metrics(eq)
            closed = [t for t in tr if t[2] != "open"]
            m.update({
                "trades": len(closed), "open_trades": len(tr) - len(closed),
                "win_rate_pct": round(100 * np.mean([t[3] > 0 for t in closed]), 1) if closed else None,
                "avg_trade_pct": round(100 * np.mean([t[3] for t in closed]), 2) if closed else None,
                "exposure_pct": round(100 * expo, 1),
                "first": str(eq.index[0].date()), "last": str(eq.index[-1].date()),
            })
            row[mode] = m
            if mode == "open":
                pd.DataFrame(tr, columns=["asset", "entry", "exit", "net_return"]).to_csv(
                    f"results/trades_{key}_{wname}.csv", index=False)
                eq.to_csv(f"results/equity_{key}_{wname}.csv", header=["equity"])
                if wname == "full":
                    curves[key] = eq
        b = buy_hold(univ, pd.Timestamp(row["open"]["first"]), FEE)
        bm = metrics(b)
        row["buy_hold"] = bm
        if wname == "full":
            eq2, _, _ = simulate(w, ws2, FEE * 2, "open")
            row["open_double_fee_total_return_pct"] = round((eq2.iloc[-1] / CAP - 1) * 100, 2)
            curves[key + "__bh"] = b
        res["windows"][wname] = row
    f, r = res["windows"]["full"], res["windows"]["recent"]
    sh_f = f["open"]["sharpe"] > f["buy_hold"]["sharpe"]
    sh_r = r["open"]["sharpe"] > r["buy_hold"]["sharpe"]
    dd_ok = f["open"]["max_dd_pct"] > f["buy_hold"]["max_dd_pct"]
    res["verdict"] = "Promising" if (sh_f and sh_r and dd_ok) else ("Failed" if (not sh_f and not sh_r) else "Mixed")
    res["dd_limit_10pct"] = "PASS" if f["open"]["max_dd_pct"] >= -10 else "BREACH"
    results[key] = res
    print(
        f"{key:24s} full {f['open']['total_return_pct']:>9}% dd {f['open']['max_dd_pct']:>7} sh {f['open']['sharpe']:>5} | "
        f"BH {f['buy_hold']['total_return_pct']:>9}% dd {f['buy_hold']['max_dd_pct']:>7} sh {f['buy_hold']['sharpe']:>5} | "
        f"recent {r['open']['total_return_pct']:>7}% sh {r['open']['sharpe']:>5} BH {r['buy_hold']['total_return_pct']:>7}% sh {r['buy_hold']['sharpe']:>5} | "
        f"2xfee {f['open_double_fee_total_return_pct']}% | tr {f['open']['trades']} win {f['open']['win_rate_pct']} => {res['verdict']} {res['dd_limit_10pct']}"
    )

json.dump(results, open("results/results.json", "w"), indent=1)
wk = {}
for k, s in curves.items():
    s2 = s.resample("W-FRI").last().dropna()
    s2 = pd.concat([s.iloc[:1], s2, s.iloc[-1:]])
    s2 = s2[~s2.index.duplicated(keep="last")]
    wk[k] = [[str(d.date()), round(float(v), 2)] for d, v in s2.items()]
json.dump(wk, open("results/curves_weekly.json", "w"))
print("wrote results/results.json and curves_weekly.json")
