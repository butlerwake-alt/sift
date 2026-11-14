# Web/social crypto strategies — NEW EXPERIMENT, run_20261113_cursor

Historical backtests of 10 publicly claimed BTC/ETH/SOL strategies found on Reddit, X, TradingView/script blogs, and trading blogs.
Paper/backtest only: no keys, no orders, no leverage, long only, no volatility sizing.
This is a **new experiment** dated 2026-11-13 (America/New_York). It does **not** reproduce or replace `research/run_20261110/`.

## What is in this folder

- `fetch.py` — Yahoo daily snapshot helper (prices in `data/`; hashes in `data/manifest.json`).
- `backtest.py` — frozen rules, simulator, verdict rule (written in the docstring **before** results were read).
- `crosscheck_vbt.py` — VectorBT re-run of Mayer and RSI/ADX with at-close fills (`results/crosscheck_vbt.txt`).
- `data/` — BTC/ETH/SOL OHLCV, Fear & Greed, funding histories + `manifest.json`.
- `results/results.json`, equity/trade CSVs, `curves_weekly.json`.

## Method (frozen)

- Signal at close *t* → fill at next open (headline). Close-fill and 2×-fee sensitivities also reported.
- Fee 0.10% per side. Long only. Idle cash earns 0.
- Windows: full history per strategy, and Nov 1, 2021 → 2026-11-12.
- Verdict: Promising = higher Sharpe than buy-and-hold in **both** windows **and** shallower full-window max DD. Failed = lower Sharpe in both. Mixed = else.
- 10% drawdown limit: PASS only if full-window max DD ≥ −10%.

## Skipped (already on SIFT)

scale-in momentum + 50-day exit, z-score mean reversion, Bollinger bounce, EMA 13/80, 30-day breakout, Halving 500, SEASONS, MACD, Bull Market Support Band, Supertrend, golden cross, Turtle 55/20.

## Run

```bash
python3 fetch.py    # optional; refreshes Yahoo prices only (new experiment if you keep outputs)
python3 backtest.py
python3 crosscheck_vbt.py
```

Re-running `fetch.py` / `backtest.py` with new data is a **new** experiment — keep this folder unchanged as the record.
