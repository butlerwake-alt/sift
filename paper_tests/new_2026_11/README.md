# New paper experiments — November 27, 2026

Frozen rules. No parameter tuning. Paper only.

| ID | Name | Category |
|----|------|----------|
| S-NEW-1 | Turn of the Month (SPY) | Stock Strategy |
| S-NEW-2 | 3 Days Down Overnight (SPY) | Stock Strategy |
| S-NEW-3 | Asset-Class Momentum Top 3 | Stock Strategy |
| S-NEW-4 | ETF Trend & Cash | Stock Strategy |
| B-NEW-1 | BTC/ETH Monthly Rotation Bot | Crypto Bot |
| B-NEW-2 | Cash-and-Carry Bot (BTC, 1x hedged) | Crypto Bot |
| B-NEW-3 | Spot Grid Bot (BTC, frozen) | Crypto Bot |
| B-NEW-4 | BTC/ETH Band Rebalance | Crypto Bot |

- Forward start: 2026-11-27, $10,000 each.
- Costs: 1.5× desk fee/slippage; idle cash earns BIL where allowed. Base-cost and doubled-cost holdouts are reported for S-NEW-4 and B-NEW-4.
- Desk drawdown limit: 10% (badge on breach; pause only if a documented risk rule requires it).
- Update: `python3 paper_tests/new_2026_11/update_daily.py` (also called from `publish.sh`). Re-runs overwrite forward ledgers deterministically (no duplicate fills).
- Site: homepage `#paper-bots`, `bots.html` (list + `?id=` detail), `scoreboard.html`.
- Does not modify existing desk strategies, `data.js` inputs, or `memescan/data/`.
- Checks: `python3 paper_tests/new_2026_11/test_new_bots.py`.
