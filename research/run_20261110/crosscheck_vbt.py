"""Cross-check (same NEW EXPERIMENT): rerun two crypto strategies in VectorBT, close fills, 0.10% fee, no cash yield."""
import importlib.util, vectorbt as vbt, pandas as pd, sys
spec=importlib.util.spec_from_file_location("bt","backtest.py")
src=open("backtest.py").read().split("results = {}; curves = {}")[0]; ns={"__file__":"backtest.py"}; exec(src,ns)
for k in ["golden_cross_btc","macd_12_26_9_btc","supertrend_10_3_btc"]:
    w=ns["STRATS"][k]["fn"]()["BTC"]; c=ns["BTC"]["Close"]; w=w[w.index>=pd.Timestamp("2016-01-01")]; c=c.reindex(w.index)
    ent=(w>0)&(w.shift(1).fillna(0)==0); ex=(w==0)&(w.shift(1).fillna(0)>0)
    pf=vbt.Portfolio.from_signals(c,ent,ex,fees=0.001,init_cash=10000,freq="1D")
    print(k, round((pf.final_value()/10000-1)*100,2), "maxdd", round(pf.max_drawdown()*100,2), "trades", pf.trades.count())
