"""VectorBT cross-check of two single-asset strategies with at-close fills.
Matches our close-fill totals within rounding when fees and signals align.
"""
import pandas as pd, numpy as np, json, os
import vectorbt as vbt

os.chdir(os.path.dirname(os.path.abspath(__file__)))
END = pd.Timestamp("2026-11-12")
FEE = 0.001
BTC = pd.read_csv("data/BTC-USD.csv", index_col=0, parse_dates=True)
BTC = BTC[BTC.index <= END]
c = BTC["Close"]

def rsi(series, n):
    d = series.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

def adx(d, n=2):
    h, l, cl = d["High"], d["Low"], d["Close"]
    up = h.diff(); down = -l.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat([(h - l), (h - cl.shift()).abs(), (l - cl.shift()).abs()], axis=1).max(axis=1)
    atr = pd.Series(tr, index=d.index).ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=d.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=d.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    return dx.ewm(alpha=1 / n, adjust=False).mean()

def state(entry, exit_):
    pos = np.zeros(len(entry)); p = 0
    for i, (e, x) in enumerate(zip(entry.values, exit_.values)):
        if p == 0 and e: p = 1
        elif p == 1 and x: p = 0
        pos[i] = p
    return pd.Series(pos, index=entry.index)

# Mayer < 2.4
mm = c / c.rolling(200).mean()
w_mayer = (mm < 2.4).astype(float).where(mm.notna(), 0.0)
# RSI/ADX
ent = (c > c.rolling(50).mean()) & (c > c.ewm(span=7, adjust=False).mean()) & (rsi(c, 2) > adx(BTC, 2))
ex = rsi(c, 2) < adx(BTC, 2)
w_rsi = state(ent, ex)

ours = json.load(open("results/results.json"))
lines = []
for key, w in [("mayer_lt_2p4_btc", w_mayer), ("rsi_adx_btc", w_rsi)]:
    # VectorBT portfolio from target weight: entries when weight rises to 1, exits to 0
    entries = (w > 0) & (w.shift(1).fillna(0) == 0)
    exits = (w == 0) & (w.shift(1).fillna(0) > 0)
    pf = vbt.Portfolio.from_signals(c, entries, exits, fees=FEE, freq="1D", init_cash=10000)
    vbt_ret = float(pf.total_return()) * 100
    our = ours[key]["windows"]["full"]["close"]["total_return_pct"]
    lines.append(f"{key}: vbt_close_fill={vbt_ret:.2f}%  ours_close_fill={our}%  diff={vbt_ret-our:.2f}pp")

txt = "\n".join(lines) + "\n"
open("results/crosscheck_vbt.txt", "w").write(txt)
print(txt)
