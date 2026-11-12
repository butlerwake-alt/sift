# Cursor prompt: SIFT backtest-by-year section + modest polish

Work in the public repo **butlerwake-alt/sift** (GitHub Pages site, live at https://butlerwake-alt.github.io/sift/). A local copy used for daily paper updates lives at `/workspace/sift_site` on Grok Bot’s box; you are opening a PR in the GitHub repo, not publishing from that box.

This is an educational **paper-trading** research board. Simulated $10,000 accounts. No live orders, no secrets, no trading-engine changes.

## What to build

Brian’s ask, in his words:

> add a section to the sift website to have all of the strategies display a section once selected to view back test data to show in a graph the time frame and how it performed. Like “back test performance 2020,2021,2022,2023,2024,2025,2026” you can select and click each year to see how that strategy performed that year.

Also do a **modest professional polish** pass so the site feels more informative and finished, without throwing away the current design.

A data file is included with this prompt: **`backtest_by_year.json`**. Copy it into the repo (recommended: repo root, or a `data/` folder). Do not regenerate the numbers. Schema and coverage notes are in the sibling `README.md`.

## Site structure (inspect these first)

Static GitHub Pages. No build step for HTML. Key files:

| File | Role |
|---|---|
| `index.html` | Home: stamp, updates teaser, regime, leaderboard, all-strategy board. |
| `strategy.html` | Detail page for one strategy (`strategy.html?n=18`). **Put the new backtest section here.** |
| `updates.html` | Full updates log. |
| `research.html` | Separate “Researched strategies” page (historical social-media backtests). Leave it working; it is not this task. |
| `app.js` | All UI. `renderStrategy()` paints `#detail` on `strategy.html`. `drawChart()` draws the **forward paper** path as SVG. `renderStamp()`, `renderUpdates()`, `renderLeaderboard()`, ranking arrows (`rankMoveHtml`) must keep working. |
| `styles.css` | Brand tokens in `:root` — black `#070605`, panel `#100e0c`, cream `#f3e2c4`, teal `#0c4550` / `#1c6d78`, green / red / yellow. Serif body, sans UI. Dark theme. |
| `data.js` | **Generated.** Defines `SIFT`. Do not edit by hand. |
| `template.json` | Descriptive text (rules, hypothesis, backtest blurb, why). `build_data.py` copies this into `data.js`. |
| `history.json` | Append-only daily **forward** paper marks. Never rewrite existing marks. |
| `ranks.json` | Daily rank snapshots for the up/down arrows. |
| `updates.json` | Updates log (newest first, capped). |
| `build_data.py` | Rebuilds `data.js` from paper-test records + `template.json`, updates the stamp and the log, writes ranks. |
| `publish.sh` | Runs `build_data.py`, validates `data.js` and `research_data.js` with Node, `git add -A`, commits and **pushes `main`** if data changed. Cache-busts `?v=` on `index.html`, `strategy.html`, `research.html`, `updates.html`. |

Forward paper chart and leaderboard stay as they are, and stay clearly labeled as forward / paper results. The new section is **historical backtest**, not those marks.

## Backtest UI (required)

On `strategy.html`, after the existing forward-paper chart and facts (or in a clearly separated block below them), add a section titled **Backtest performance**.

1. **Label, always visible:** “Backtest (hypothetical, includes costs)”. Phrase it so nobody can mistake it for the live paper account. One short line of method: signal on the close, fill at the next close, costs as given in the JSON (`costs` / `fill`). Mention 2026 is year-to-date through the last backtest bar.

2. **Year controls:** buttons or tabs for `2020` `2021` `2022` `2023` `2024` `2025` `2026` plus **All**. Large enough to tap on a phone; wrap on a narrow screen. The selected year is obvious.

3. **Chart:** a line chart of backtest equity for the selected range, starting at $10,000 (rebase a year slice with `10000 / startEquity` as described in the data README). Overlay the matching buy-and-hold benchmark from `benchmarks` (SPY, QQQ, or BTC per `strategy.benchmark`) over the same dates, also rebased to $10,000. Use a dashed benchmark line, consistent with the existing legend style.

4. **Per-year stats** next to or under the chart: return, max drawdown, trade count, and the benchmark return (and a vs-benchmark gap). If `complete` is `false`, say so (partial year or 2026 YTD) and show `startDate`–`endDate`.

5. **All tab:** use `equityFrom2020` (not the native pre-2020 path). Stats for that window can be computed from the first and last points, or from compounding the year returns; either is fine if you label the window.

6. **Empty states:**
   - `hasBacktest` is false (#2, #3, #7, #8): no chart. Show `gapReason` verbatim.
   - A year value is `null`: that year’s button is disabled or, if selected, shows “No backtest data for this year” (for example 2020 on #1, #4, #5, #9; every year but 2026 on #10).
   - Render `caveats` under the chart (survivorship on #9, BTC-only vs 5-coin basket on #1, tiny sample on #6, short window on #10, and so on).

7. **Do not** add backtest CAGR or year returns to the home-page leaderboard or the “best to worst” ranking. Those stay forward-paper only.

## Chart implementation notes

The existing `drawChart()` in `app.js` is **not** reusable as-is for this:

- Its y-axis is a fixed paper-account band (`SIFT.moneyMin`–`SIFT.moneyMax`, about $8,800–$10,600). Backtests run to tens or hundreds of thousands of dollars and must **auto-scale**.
- It draws a large SVG circle on every point. Fine for a handful of forward marks; unusable for 1,500+ daily bars. For the backtest chart, draw a polyline (and maybe end dots or a hover readout), not a dot per day.

You may extend the existing SVG approach with auto y-scale and date ticks, or use a lightweight library from a public CDN (Chart.js is fine). No new paid services, no npm build step unless you can explain why a static Pages site needs one. Vanilla canvas/SVG is preferred.

Default the selected year to **All**, or to the latest year that has data (2026) — pick one and keep it consistent.

The JSON is ~2.6 MB. Load it once (same-origin fetch of `backtest_by_year.json?v=…`, or wrap it once as `backtest_by_year.js` setting `window.SIFT_BACKTEST`). Do not inline it into `data.js`. If you add a script tag, give it the same `?v=` cache-bust pattern already used on CSS/JS, and if you add a new HTML page to `publish.sh`’s sed list, leave the rest of that script alone.

## Modest polish (do not redesign from scratch)

Keep the brand, dark theme, SIFT lockup, and current information architecture. Reasonable touches:

- Tighten spacing, hierarchy, and typography on `strategy.html` so rules, “why we picked this”, forward results, and the new backtest section read as one professional page.
- Make sure the Last-updated stamp, “All updates” link, and nav still appear and work on every page.
- Small home-page cleanups are welcome (alignment, mobile nav, card/leaderboard readability) but do not remove or hide the ranking, regime box, or updates teaser.
- Accessibility: visible focus states already exist; keep them. Year buttons should be real `<button>`s with an `aria` selected state. The chart needs an `aria-label` or a text summary of the selected year’s return and drawdown.

## Hard rules

- Static GitHub Pages only. No server, no secrets, no `.env`, no API keys.
- Do **not** break `build_data.py`, `publish.sh`, the best-to-worst ranking, the Last-updated stamp (including the amber stale state when data is more than two days old), or the updates log (`updates.json` / `updates.html` / the three newest on the home page).
- Do **not** edit `data.js` by hand. Do **not** rewrite marks in `history.json`. Do **not** change trading or paper-engine code.
- Do **not** push to `main`. Do **not** run `publish.sh` (it commits and pushes `main`).
- Paper only. Do not add language that this is a forecast, a recommendation, or live performance.
- If you must touch `publish.sh` (for example to cache-bust a new asset), keep its “no data change → don’t push” behavior and its validation of `data.js` / `research_data.js`.

## Git workflow

1. Branch from the current `main` (for example `feature/backtest-by-year`).
2. Commit the data file, the UI, and any CSS/HTML on that branch.
3. Open a pull request against `main` with a short description and screenshots (desktop and a phone-width viewport) of at least:
   - a stock strategy with a full history (e.g. #11),
   - a crypto strategy (e.g. #23),
   - a partial-history strategy (e.g. #4 or #10),
   - a no-backtest strategy (#2, #3, #7, or #8),
   - the forward-paper chart still visible and clearly distinct.
4. Stop there. Grok Bot will review the PR and publish.

## Acceptance checklist

- [ ] Clicking a strategy on the board still opens `strategy.html?n=…` and shows the forward paper path, rules, why, stamp, and updates link.
- [ ] A “Backtest performance” section is on every strategy detail page.
- [ ] Year buttons 2020–2026 and All work; the chart and stats update on click without a page reload.
- [ ] All tab shows the 2020–2026 (or first-available) path starting at $10,000, with a benchmark overlay.
- [ ] Each year shows return, max drawdown, trades, and vs-benchmark, with YTD / partial labels where `complete` is false.
- [ ] Years with `null` and strategies with `hasBacktest: false` fail gracefully using `gapReason` / a no-data message. No invented curves.
- [ ] The section is clearly labeled “Backtest (hypothetical, includes costs)” and is visually distinct from forward/paper results.
- [ ] Mobile: year buttons wrap and are tappable; the chart is readable; no horizontal page blowout.
- [ ] Leaderboard ranking, Last-updated stamp (including amber stale), and updates log still work on home, strategy, and updates pages.
- [ ] `node` validation used in `publish.sh` still passes (`data.js` has 26 strategies with points and `why`; `research_data.js` still parses). You can run those two `node -e` checks locally without running `publish.sh`.
- [ ] No secrets, no paid services, no push to `main`. PR is open with screenshots.
