# Web/social strategies — NEW EXPERIMENT, run 2026-11-10 (ET)

Historical backtests of 10 publicly shared strategies. Paper/backtest only: no keys, no orders, no leverage, long only, no volatility sizing.
This is a new experiment; it does not reproduce or replace any earlier SIFT evidence.

- `fetch.py` — snapshot of Yahoo daily data into `data/` (hashes in `data/manifest.json`, retrieved 2026-11-10 11:27 ET).
- `backtest.py` — all rules, the simulator, and the verdict rule (written in the docstring before the run). Output: `results/results.json`,
  `results/equity_*`, `results/trades_*`, `results/curves_weekly.json`.
- `crosscheck_vbt.py` — VectorBT re-run of three Bitcoin strategies with at-close fills; matches our at-close numbers within rounding (`results/crosscheck_vbt.txt`).
- Last bar used: 2026-11-09 (the Nov 10 bar was still forming and is dropped).
- Headline = next-open fills; sensitivity = signal-close fills and doubled fees.

Run: `/workspace/qvenv/bin/python fetch.py && /workspace/qvenv/bin/python backtest.py`
(re-running fetch.py gets new data and is a NEW experiment; keep this folder unchanged as the record.)
