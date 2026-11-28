# New paper experiments — November 27, 2026

Frozen rules. No parameter tuning. Paper only.

| ID | Name | Category |
|----|------|----------|
| S-NEW-1 | Turn of the Month (SPY) | Stock Strategy |
| S-NEW-2 | 3 Days Down Overnight (SPY) | Stock Strategy |
| S-NEW-3 | Asset-Class Momentum Top 3 | Stock Strategy |
| B-NEW-1 | BTC/ETH Monthly Rotation Bot | Crypto Bot |
| B-NEW-2 | Cash-and-Carry Bot (BTC, 1x hedged) | Crypto Bot |
| B-NEW-3 | Spot Grid Bot (BTC, frozen) | Crypto Bot |

- Forward start: 2026-11-27, $10,000 each.
- Costs: 1.5× desk fee/slippage; idle cash earns BIL where allowed.
- Desk drawdown limit: 10% (badge on breach).
- Update: `python3 paper_tests/new_2026_11/update_daily.py` (also called from `publish.sh`).
- Does not modify existing desk strategies, `data.js` inputs, or `memescan/data/`.
