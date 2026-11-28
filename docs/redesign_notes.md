# Redesign notes — patterns worth borrowing

Research pass across Finviz, Koyfin, TradingView, Seeking Alpha, Motley Fool, and TradingTheTrend. Borrow patterns, not copy (and skip hype claims).

## Dark theme and color

- **TradingView / Koyfin / Finviz (pro mode):** near-black canvas, blue-gray panels, one cool accent. Green and red are reserved for up/down — never decoration.
- **Seeking Alpha / Motley Fool:** light surfaces work too; hierarchy comes from a dark sticky app bar + white panels, same green/red semantics.
- **SIFT takeaway:** keep dark as default, light as a toggle. One accent (cool teal/blue). `--up` / `--down` / `--flat` only for performance.

## Card layouts

- Cards are a **second layer** (featured name, filing, idea), not the whole ranking.
- Finviz and Koyfin put the ranked list in a **real table**; TradingTheTrend and Motley Fool lead with a **scoreboard**, then detail.
- **SIFT takeaway:** top 3–5 strategies as large performance cards; everyone else in a dense sortable table.

## Leaderboards and top performers first

- Motley Fool and TradingTheTrend put the **track-record board above the story**.
- TradingTheTrend publishes a year-by-year win table and a trade log; Motley Fool pairs a return with a **window**.
- Morningstar / Seeking Alpha **label** what a figure is (quant vs analyst, as-of date).
- **SIFT takeaway:** homepage opens on **Top Strategies** ranked by forward paper return. Short windows stay labeled **too early to tell**. No invented win rates — closed-trade win rate is not in `data.js`, so the board shows **Up days** (share of daily marks that rose) from the same equity path.

## Ticker strips

- Finviz and TradingView open with a **moving tape**: symbol, last, % change, tiny spark, green/red.
- The tape is **context**, not the product.
- **SIFT takeaway:** keep the crypto tape above the sticky nav; do not crowd it with fake yields.

## Typography and density

- Pro boards use a **plain sans** for the board and **tabular figures** for every number. Motley Fool / Seeking Alpha use a slightly more editorial display for headlines.
- Dense tables need air: sticky header, sort affordance, row sparklines (TradingView watchlists, Finviz maps).
- **SIFT takeaway:** IBM Plex Sans + IBM Plex Mono for numbers; brand lockup stays the hero signal; serif reserved for long essays (QQQI).

## Trust labels (steal this, skip the hype)

- Print **as-of**, **paper-only**, and **source** next to every board.
- Empty modules say **coming soon** with **no figures** (Unusual Whales / Quiver pattern).
- TradingTheTrend’s public scoreboard pattern is useful; its marketing win-rate claims are **not** — SIFT stays anonymous and paper-only.

## Navigation

- Sticky top bar + phone bottom tab bar (Robinhood / Public pattern).
- One prominent **Meme Coins** entry (header CTA + homepage) into the existing memescan paper board: open positions, closed trades, P&L, win rate from repo data.
