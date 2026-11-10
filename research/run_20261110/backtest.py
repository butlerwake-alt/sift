"""NEW EXPERIMENT dated 2026-11-10 — historical backtests of publicly shared strategies.
Paper/backtest only. No keys, no orders, no leverage, long-only, no volatility sizing.
Signals use data through close t only. Headline fills: NEXT OPEN (t+1). Sensitivity: fill at signal close
(the timing most sources assume). Fees: stocks/ETFs 0.05% per side, crypto 0.10% per side, on every traded dollar.
Idle cash in stock strategies earns 13-week T-bill yield (^IRX); crypto idle cash earns 0.
Sharpe: stock family on daily excess return over T-bills (252/yr); crypto on raw daily return (365/yr).
VERDICT RULE (written before running):
  Promising = Sharpe above buy-and-hold in BOTH the full and recent windows AND full-window max drawdown shallower than buy-and-hold.
  Failed    = Sharpe below buy-and-hold in BOTH windows.
  Mixed     = everything else.
  10% drawdown limit: PASS only if full-window max drawdown (daily closes) is no worse than -10%.
"""
import pandas as pd, numpy as np, json, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
END = pd.Timestamp("2026-11-09")       # drop the still-forming Nov 10 bar
RECENT = pd.Timestamp("2024-11-11")    # recent 2-year window start (first trading day on/after Nov 10, 2024)
def load(t):
    d = pd.read_csv(f"data/{t}.csv", index_col=0, parse_dates=True); return d[d.index <= END]
SPY, EFA, AGG, IRX, BTC = (load(t) for t in ["SPY","EFA","AGG","IRX","BTC-USD"])
tbill_daily = (IRX["Close"]/100/252).reindex(SPY.index).ffill().fillna(0)

# ---------- indicators ----------
def rsi(c, n):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + up/dn)
def state_machine(entry, exit_):
    pos = np.zeros(len(entry)); p = 0
    for i, (e, x) in enumerate(zip(entry.values, exit_.values)):
        if p == 0 and e: p = 1
        elif p == 1 and x: p = 0
        pos[i] = p
    return pd.Series(pos, index=entry.index)
def atr_rma(d, n):
    pc = d["Close"].shift(); tr = pd.concat([d["High"]-d["Low"], (d["High"]-pc).abs(), (d["Low"]-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
def supertrend_dir(d, n=10, m=3.0):
    hl2 = (d["High"]+d["Low"])/2; a = atr_rma(d, n); c = d["Close"].values
    bu = (hl2 + m*a).values; bl = (hl2 - m*a).values; up = bu.copy(); lo = bl.copy(); dirn = np.zeros(len(d)); st = np.zeros(len(d))
    for i in range(len(d)):
        if i == 0 or np.isnan(a.values[i-1]): dirn[i] = -1; st[i] = up[i]; continue
        up[i] = bu[i] if (bu[i] < up[i-1] or c[i-1] > up[i-1]) else up[i-1]
        lo[i] = bl[i] if (bl[i] > lo[i-1] or c[i-1] < lo[i-1]) else lo[i-1]
        if st[i-1] == up[i-1]: dirn[i] = 1 if c[i] > up[i] else -1
        else: dirn[i] = -1 if c[i] < lo[i] else 1
        st[i] = lo[i] if dirn[i] == 1 else up[i]
    return pd.Series((dirn == 1).astype(float), index=d.index)
def month_end_flags(idx):
    s = pd.Series(idx, index=idx); return s.groupby([idx.year, idx.month]).transform("max") == s

# ---------- strategies: each returns a dict asset->weight Series (decided at close t) ----------
def s_rsi2():
    c = SPY["Close"]; ent = (c > c.rolling(200).mean()) & (rsi(c, 2) < 5); ex = c > c.rolling(5).mean()
    return {"SPY": state_machine(ent, ex)}
def s_faber():
    c = SPY["Close"]; me = month_end_flags(c.index); m = c[me]; sma10 = m.rolling(10).mean()
    sig = (m > sma10).astype(float).where(sma10.notna(), 0.0)
    return {"SPY": sig.reindex(c.index).ffill().fillna(0)}
def s_golden():
    c = BTC["Close"]; return {"BTC": ((c.rolling(50).mean() > c.rolling(200).mean())).astype(float)}
def s_turtle():
    d = BTC; ent = d["Close"] > d["High"].rolling(55).max().shift(); ex = d["Close"] < d["Low"].rolling(20).min().shift()
    return {"BTC": state_machine(ent, ex)}
def s_macd():
    c = BTC["Close"]; macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); sig = macd.ewm(span=9, adjust=False).mean()
    w = (macd > sig).astype(float); w.iloc[:35] = 0; return {"BTC": w}
def s_super(): return {"BTC": supertrend_dir(BTC, 10, 3.0)}
def s_ibs():
    d = SPY; ibs = (d["Close"]-d["Low"])/(d["High"]-d["Low"]).replace(0, np.nan)
    return {"SPY": state_machine(ibs < 0.2, ibs > 0.8)}
def s_tom():
    idx = SPY.index; g = pd.Series(np.arange(len(idx)), index=idx).groupby([idx.year, idx.month])
    rank_from_end = g.rank(ascending=False, method="first"); rank_from_start = g.rank(method="first")
    # hold from the close of the 2nd-to-last trading day (to earn the last day) to the close of the 3rd trading day
    hold = (rank_from_end <= 2) | (rank_from_start <= 2)   # weight at close t applies to day t+1
    w = hold.astype(float); w[(rank_from_end == 1)] = 1; return {"SPY": w}
def s_bmsb():
    c = BTC["Close"]; wk = c.resample("W-SUN").last(); wk = wk[wk.index <= END]
    sma = wk.rolling(20).mean(); ema = wk.ewm(span=21, adjust=False).mean(); hi = np.maximum(sma, ema); lo = np.minimum(sma, ema)
    st = state_machine((wk > hi) & sma.notna(), wk < lo)
    st.index = st.index  # Sunday close = weekly close; weight known at that daily bar
    return {"BTC": st.reindex(c.index).ffill().fillna(0)}
def s_gem():
    idx = SPY.index.intersection(EFA.index).intersection(AGG.index); me = month_end_flags(idx)
    tb = (1 + tbill_daily.reindex(idx)).cumprod()
    m = pd.DataFrame({"SPY": SPY["Close"].reindex(idx), "EFA": EFA["Close"].reindex(idx), "TB": tb})[me]
    r12 = m / m.shift(12) - 1
    W = pd.DataFrame(0.0, index=m.index, columns=["SPY","EFA","AGG"])
    for t, r in r12.iterrows():
        if r.isna().any(): continue
        if r["SPY"] > r["TB"]: W.loc[t, "SPY" if r["SPY"] >= r["EFA"] else "EFA"] = 1
        else: W.loc[t, "AGG"] = 1
    W = W.reindex(idx).ffill().fillna(0)
    return {k: W[k] for k in W}

STRATS = {
 "rsi2_connors": dict(fn=s_rsi2, mkt="SPY", fee=0.0005), "faber_10m_sma": dict(fn=s_faber, mkt="SPY", fee=0.0005),
 "ibs_reversion": dict(fn=s_ibs, mkt="SPY", fee=0.0005), "turn_of_month": dict(fn=s_tom, mkt="SPY", fee=0.0005),
 "gem_dual_momentum": dict(fn=s_gem, mkt="SPY", fee=0.0005),
 "golden_cross_btc": dict(fn=s_golden, mkt="BTC", fee=0.001), "turtle_55_20_btc": dict(fn=s_turtle, mkt="BTC", fee=0.001),
 "macd_12_26_9_btc": dict(fn=s_macd, mkt="BTC", fee=0.001), "supertrend_10_3_btc": dict(fn=s_super, mkt="BTC", fee=0.001),
 "bmsb_btc": dict(fn=s_bmsb, mkt="BTC", fee=0.001),
}
PX = {"SPY": SPY, "EFA": EFA, "AGG": AGG, "BTC": BTC}
START = {"SPY": pd.Timestamp("2000-01-03"), "BTC": pd.Timestamp("2016-01-01")}

def simulate(weights, start, fee, mode, cash_yield):
    """weights: dict asset->Series decided at close t. Returns daily equity Series (start=10000) and trade list."""
    assets = list(weights); idx = None
    for a in assets:
        ix = PX[a].index; idx = ix if idx is None else idx.intersection(ix)
    idx = idx[idx >= start]
    W = pd.DataFrame({a: weights[a].reindex(idx).fillna(0) for a in assets})
    O = pd.DataFrame({a: PX[a]["Open"].reindex(idx) for a in assets}); C = pd.DataFrame({a: PX[a]["Close"].reindex(idx) for a in assets})
    cy = cash_yield.reindex(idx).fillna(0) if cash_yield is not None else pd.Series(0.0, index=idx)
    eq = 10000.0; held = {a: 0.0 for a in assets}  # weight held
    out = [eq]; trades = []; open_tr = {}
    Wv = W.values; Ov = O.values; Cv = C.values
    # day 0: decide at close of day 0 (no position before start)
    def rebalance(i, price_row, target):
        nonlocal eq
        turnover = sum(abs(target[j] - held[a]) for j, a in enumerate(assets))
        eq_before = eq; eq *= (1 - fee*turnover)
        for j, a in enumerate(assets):
            if held[a] == 0 and target[j] > 0: open_tr[a] = (idx[i], eq_before, price_row[j])
            if held[a] > 0 and target[j] == 0 and a in open_tr:
                d0, e0, p0 = open_tr.pop(a); trades.append((a, str(d0.date()), str(idx[i].date()), (price_row[j]/p0)*(1-fee)**2 - 1))
            held[a] = target[j]
    if mode == "close": rebalance(0, Cv[0], Wv[0])
    for i in range(1, len(idx)):
        if mode == "open":
            # overnight on yesterday's holding, then trade at open toward weight decided at close i-1, then intraday
            r_on = sum(held[a]*(Ov[i][j]/Cv[i-1][j]-1) for j, a in enumerate(assets))
            eq *= 1 + r_on + (1-sum(held.values()))*0  # cash interest applied once below
            rebalance(i, Ov[i], Wv[i-1])
            r_id = sum(held[a]*(Cv[i][j]/Ov[i][j]-1) for j, a in enumerate(assets))
            eq *= 1 + r_id + (1-sum(held.values()))*cy.iloc[i]
        else:
            r = sum(held[a]*(Cv[i][j]/Cv[i-1][j]-1) for j, a in enumerate(assets))
            eq *= 1 + r + (1-sum(held.values()))*cy.iloc[i]
            rebalance(i, Cv[i], Wv[i])
        out.append(eq)
    # mark open trades at last close (not force-closed; reported as open)
    for a, (d0, e0, p0) in open_tr.items():
        j = assets.index(a); trades.append((a, str(d0.date()), "open", Cv[-1][j]/p0*(1-fee) - 1))
    exposure = (W.shift(1).fillna(0).sum(axis=1) > 0).mean() if mode=="open" else (W.sum(axis=1) > 0).mean()
    return pd.Series(out, index=idx), trades, float(exposure)

def bh(asset, start, fee):
    c = PX[asset]["Close"]; o = PX[asset]["Open"]; c = c[c.index >= start]; o0 = o[o.index >= start].iloc[0]
    eq = 10000*(1-fee)*c/o0; return eq
def metrics(eq, ann, rf=None):
    r = eq.pct_change().dropna(); yrs = (eq.index[-1]-eq.index[0]).days/365.25
    if rf is not None: r = r - rf.reindex(r.index).fillna(0)   # Sharpe on excess return over T-bills (stock family)
    dd = (eq/eq.cummax()-1).min()
    dd = min(dd, eq.iloc[0]/10000-1, 0)
    return {"total_return_pct": round((eq.iloc[-1]/10000-1)*100, 2),
            "cagr_pct": round(((eq.iloc[-1]/10000)**(1/yrs)-1)*100, 2), "max_dd_pct": round(dd*100, 2),
            "sharpe": round(r.mean()/r.std()*np.sqrt(ann), 2) if r.std() > 0 else 0.0, "final": round(float(eq.iloc[-1]), 2)}

results = {}; curves = {}
os.makedirs("results", exist_ok=True)
for key, S in STRATS.items():
    w = S["fn"](); mkt = S["mkt"]; ann = 252 if mkt == "SPY" else 365; cyld = tbill_daily if mkt == "SPY" else None
    start = START[mkt] if key != "gem_dual_momentum" else pd.Timestamp("2004-10-01")
    res = {"market": mkt, "fee_per_side_pct": S["fee"]*100, "windows": {}}
    for wname, ws in [("full", start), ("recent", RECENT)]:
        row = {}
        for mode in ["open", "close"]:
            eq, tr, expo = simulate(w, ws, S["fee"], mode, cyld)
            m = metrics(eq, ann, cyld); closed = [t for t in tr if t[2] != "open"]
            m.update({"trades": len(closed), "open_trades": len(tr)-len(closed),
                      "win_rate_pct": round(100*np.mean([t[3] > 0 for t in closed]), 1) if closed else None,
                      "avg_trade_pct": round(100*np.mean([t[3] for t in closed]), 2) if closed else None,
                      "exposure_pct": round(100*expo, 1), "first": str(eq.index[0].date()), "last": str(eq.index[-1].date())})
            row[mode] = m
            if mode == "open":
                pd.DataFrame(tr, columns=["asset","entry","exit","net_return"]).to_csv(f"results/trades_{key}_{wname}.csv", index=False)
                eq.to_csv(f"results/equity_{key}_{wname}.csv", header=["equity"])
                if wname == "full": curves[key] = eq
        b = bh(mkt, row["open"]["first"], S["fee"]); b = b[b.index >= pd.Timestamp(row["open"]["first"])]
        bm = metrics(b, ann, cyld); row["buy_hold"] = bm
        if wname == "full":
            eq2, _, _ = simulate(w, ws, S["fee"]*2, "open", cyld); row["open_double_fee_total_return_pct"] = round((eq2.iloc[-1]/10000-1)*100, 2)
        if wname == "full": curves[key + "__bh"] = b
        res["windows"][wname] = row
    f, r = res["windows"]["full"], res["windows"]["recent"]
    sh_f = f["open"]["sharpe"] > f["buy_hold"]["sharpe"]; sh_r = r["open"]["sharpe"] > r["buy_hold"]["sharpe"]
    dd_ok = f["open"]["max_dd_pct"] > f["buy_hold"]["max_dd_pct"]
    res["verdict"] = "Promising" if (sh_f and sh_r and dd_ok) else ("Failed" if (not sh_f and not sh_r) else "Mixed")
    res["dd_limit_10pct"] = "PASS" if f["open"]["max_dd_pct"] >= -10 else "BREACH"
    results[key] = res
    print(f"{key:22s} full {f['open']['total_return_pct']:>9}% dd {f['open']['max_dd_pct']:>7} sh {f['open']['sharpe']:>5} | BH {f['buy_hold']['total_return_pct']:>9}% dd {f['buy_hold']['max_dd_pct']:>7} sh {f['buy_hold']['sharpe']:>5} | recent {r['open']['total_return_pct']:>7}% sh {r['open']['sharpe']:>5} BH {r['buy_hold']['total_return_pct']:>7}% sh {r['buy_hold']['sharpe']:>5} | close-fill full {f['close']['total_return_pct']}% | 2xfee {f['open_double_fee_total_return_pct']}% | tr {f['open']['trades']} win {f['open']['win_rate_pct']} exp {f['open']['exposure_pct']} => {res['verdict']} {res['dd_limit_10pct']}")
json.dump(results, open("results/results.json", "w"), indent=1)
# weekly-sampled curves for the website
wk = {}
for k, s in curves.items():
    s2 = s.resample("W-FRI").last().dropna(); s2 = pd.concat([s.iloc[:1], s2, s.iloc[-1:]]); s2 = s2[~s2.index.duplicated(keep="last")]
    wk[k] = [[str(d.date()), round(float(v), 2)] for d, v in s2.items()]
json.dump(wk, open("results/curves_weekly.json", "w"))
