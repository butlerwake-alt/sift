"""NEW EXPERIMENT 2026-11-10: snapshot public daily data (Yahoo via yfinance). No keys."""
import yfinance as yf, pandas as pd, hashlib, json, datetime as dt, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
man={"retrieved_et":dt.datetime.now().strftime("%Y-%m-%d %H:%M %Z"),"source":"Yahoo Finance via yfinance, auto_adjust=True (split/dividend adjusted OHLC)","files":{}}
for t in ["SPY","EFA","AGG","^IRX","BTC-USD"]:
    d=yf.download(t,start="1993-01-01",auto_adjust=True,progress=False)
    if isinstance(d.columns,pd.MultiIndex): d.columns=d.columns.get_level_values(0)
    d=d[["Open","High","Low","Close","Volume"]].dropna(subset=["Close"])
    d.index=pd.to_datetime(d.index).tz_localize(None)
    f=f"data/{t.replace('^','')}.csv"; d.to_csv(f)
    man["files"][f]={"rows":len(d),"first":str(d.index[0].date()),"last":str(d.index[-1].date()),"sha256":hashlib.sha256(open(f,'rb').read()).hexdigest()}
json.dump(man,open("data/manifest.json","w"),indent=1); print(json.dumps(man,indent=1))
