"""Snapshot Yahoo daily OHLCV + public Fear&Greed + funding into data/.
NEW EXPERIMENT run_20261113_cursor. Re-running creates a NEW experiment; keep this folder frozen.
"""
import hashlib, json, os
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("data", exist_ok=True)

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

man = {"retrieved_utc": datetime.now(timezone.utc).isoformat(), "tickers": {}}
today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()

for t in ["BTC-USD", "ETH-USD", "SOL-USD"]:
    d = yf.download(t, start="2014-01-01", progress=False, auto_adjust=True)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    d = d[["Open", "High", "Low", "Close", "Volume"]].dropna()
    d = d[d.index < today]
    path = f"data/{t}.csv"
    d.to_csv(path)
    man["tickers"][t] = {
        "rows": len(d), "first": str(d.index[0].date()), "last": str(d.index[-1].date()),
        "sha256": sha(path), "source": "Yahoo Finance via yfinance",
    }
    print(t, len(d), d.index[0].date(), d.index[-1].date())

# Fear & Greed and funding are assembled once in this run (see data/manifest.json sources).
# Do not overwrite them here so re-fetching prices does not silently change alt series mid-experiment.
if os.path.exists("data/manifest.json"):
    old = json.load(open("data/manifest.json"))
    for k, v in old.get("tickers", {}).items():
        if k not in man["tickers"]:
            man["tickers"][k] = v
json.dump(man, open("data/manifest.json", "w"), indent=2)
print("wrote data/manifest.json")
