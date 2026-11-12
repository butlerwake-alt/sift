# SIFT backtest-by-year handoff

Prepared 11 Nov 2026, 7:39 PM ET (America/New_York) for a Cursor agent adding a per-strategy **Backtest performance** section to https://butlerwake-alt.github.io/sift/.

Paper / hypothetical only. This folder is **not** the live site repo. Do not copy these files into `/workspace/sift_site` or run `publish.sh` from here.

| File | What it is |
|---|---|
| `backtest_by_year.json` | Daily equity curves and calendar-year stats for all 26 strategies (about 2.6 MB; under the 5 MB cap, so not downsampled). |
| `CURSOR_PROMPT.md` | Self-contained prompt for a Cursor agent working in `butlerwake-alt/sift`. |
| `build_backtest_by_year.py` | Reproducible builder. Re-run with `/workspace/qvenv/bin/python build_backtest_by_year.py` if the frozen lab curves are refreshed. |

## Coverage

- **22 / 26** strategies have a daily equity curve starting at $10,000.
- **17 / 26** have complete calendar years 2020–2025, plus 2026 year-to-date: #6 and #11–#26.
- **5 / 26** are partial: #1, #4, #5, #9 start 1 Nov 2021 (2020 is `null`, 2021 is a partial year); #10 is only 59 sessions, 17 Aug–6 Nov 2026.
- **4 / 26** have no exact-rule backtest. Years are `null`. Show a plain message, do not invent a chart.
  - #2 Crypto z-score mean reversion — no backtest of these exact rules.
  - #3 Crypto Bollinger band reversion — forward-only.
  - #7 SEASONS — rules still being built; not running.
  - #8 S&P 500 dip-buy — no backtest for this equity version.

Headline CAGR, max drawdown and (almost all) trade counts match the site cards within 0.2 points. Known wrinkles:

- **#12** trade count is 1,729 in the trades CSV vs 1,727 on the site / in `results.json` (off by two). Returns and drawdown match.
- Several lab CAGRs round to one decimal a tenth away from the card (for example #15 83.1 vs 83.0, #17 16.7 vs 16.8).
- **#4 / #5 / #9** site blurbs quote *total* return over Nov 2021–Nov 2026, not CAGR (`full.totalReturnPct` is the comparable figure).
- **#6** site blurbs quote per-cycle returns and a fresh $10,000 from 1 Nov 2021 (+545.7%, max DD −28.1%). `full` is the continuous account from 17 Sep 2014 and is much larger; use `equityFrom2020` and the year tabs for 2020–2026, and `freshFrom2021` if you mention that window.
- **#1** is the published *BTC-only* scale-in + 50-day-exit path (+203.4%, −21.7%). The live paper basket is five coins; that basket backtest was +128.2% / −36.1% and is not the site headline.
- **#9** has survivorship bias (today’s Nasdaq-100 members). The site already warns not to trust the +749% figure.
- Costs are not identical across the book: labs #11–#21 use 0.05%/side (stocks) and #13, #15, #16, #22–#26 use 0.25%/side (crypto). Early social-paper tests #4–#6 use 0.10% fee plus 0.10% slippage per side; #1 uses 0.10%/side; #9 uses 0.10%/side; #10 uses 0.03%/side.

## Schema

Top-level keys: `meta`, `coverage`, `benchmarks`, `strategies`.

### `benchmarks`

`SPY`, `QQQ`, and `BTC`. Each has `years` (2020–2026) and `equityFrom2020.points`: an array of `[ "YYYY-MM-DD", equity ]` starting at $10,000 at the last 2019 close (so 2020’s first bar already shows that day’s move). Buy-and-hold, no ongoing costs.

A strategy’s `benchmark` field is `"SPY"`, `"QQQ"`, `"BTC"`, or `"SPY_QQQ_50_50"` (#10 only; there is no shared series — use the per-year `benchReturnPct` and, if you need a line, the strategy’s own window).

### Each `strategies[]` entry

| Field | Meaning |
|---|---|
| `n`, `name`, `kind` | Strategy number, site name, `stock` or `crypto`. |
| `hasBacktest` | `false` for #2, #3, #7, #8. |
| `coverage` | `full` (2020–2025 complete + 2026 YTD), `partial`, or `none`. |
| `gapReason` | Present when `coverage` is `none`. Use this text on the page. |
| `costs`, `fill`, `caveats` | Show near the chart. |
| `benchmark` | Key into `benchmarks`, except #10. |
| `years` | Object with keys `"2020"` … `"2026"`. Value is `null` when there is no history that year, otherwise the stats below. |
| `equity` | Native curve, $10,000 at the first backtest date (may start before 2020). |
| `equityFrom2020` | Same path rebased to $10,000 at the last pre-2020 close, or at the first bar if the test starts later. **Prefer this for the All tab.** |
| `full` | Whole-sample stats vs the $10,000 start. `cagrPct` is omitted when the window is shorter than a year. |
| `siteBacktest` / `siteMatch` | Cited site figures and a check against this file. |

### A non-null year object

```json
{
  "returnPct": 55.4,
  "maxDdPct": -15.7,
  "trades": 51,
  "benchReturnPct": 18.3,
  "benchMaxDdPct": -33.7,
  "startEquity": 22455.93,
  "endEquity": 34907.52,
  "startDate": "2020-01-02",
  "endDate": "2020-12-31",
  "complete": true
}
```

- `returnPct` is the calendar-year return of the running account (last close of the prior year → last close of this year), already including costs. It is *not* a fresh $10,000 started on 1 January, except in the first year of a test.
- `maxDdPct` is the peak-to-trough drawdown along that same path inside the year (peak reset at the prior close).
- `trades` uses `tradeCountMethod`: `closed_exits` for labs #11–#26, `fills` for #4–#6, #9, #10, and `flat_to_flat_episodes` for #1.
- `complete` is `false` for 2026 (always YTD through the last backtest bar) and for any mid-year start (for example 2021 for #1, #4, #5, #9).
- To draw a year path rebased to $10,000, slice `equity.points` (or `equityFrom2020.points`) between `startDate` and `endDate` and scale by `10000 / startEquity`.

Percentages are one decimal; equity is cents. Dates are `YYYY-MM-DD`.
