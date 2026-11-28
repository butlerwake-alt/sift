# Redesign notes — patterns to borrow

Looked at Finviz, Koyfin, TradingView, Seeking Alpha, Motley Fool, and TradingTheTrend. Goal: make SIFT feel like a polished trading research desk without inventing numbers or adding a build step.

## Dark theme and color use

- **Finviz / TradingView / Koyfin:** Near-black canvas, slate elevated panels, one cool accent (blue) for links and chrome. Green and red are reserved for up/down — never decoration.
- **Seeking Alpha:** Light app shell with a dense index strip; same green/red meaning on movers.
- **Motley Fool:** Marketing-first light pages; performance scoreboards lead with one big number and a comparison line (service vs S&P).
- **SIFT adopt:** Keep dark-first with a light toggle. Accent stays teal/blue. Green/red/yellow only for return, P&L, and flat. Pair color with a sign (`+` / `−`) so color is never the only cue.

## Card layouts

- **TradingView / Motley Fool:** Hero cards for a short list of “what matters now” (top ideas, top movers), then denser content below.
- **Koyfin:** Cards for dashboards and modules; the ranking itself stays tabular.
- **TradingTheTrend:** Big stat blocks (win rate, trade count, years) above a documented log.
- **SIFT adopt:** Top 3–5 forward strategies as large ranked cards (name, return, win rate, max drawdown, sparkline). Everything else stays in a table. Meme Coins uses summary cards for open / closed / P&L / win rate, then lists.

## Leaderboards

- **Finviz:** Gainers/losers tables up front — rank, ticker, change %, volume. Sortable columns, sticky headers, tabular figures.
- **TradingTheTrend:** Year-by-year scoreboard before the pitch; every trade logged.
- **Motley Fool:** “Top 10” / track-record window next to the return so the figure is labeled, not hyped.
- **SIFT adopt:** Leaderboard is the first real module after a short brand line. Default sort = paper return. Show forward window and “too early to tell” under 90 days. No mixing backtest ranks into the forward board.

## Ticker strips

- **Finviz / TradingView:** A live tape of symbols with green/red change and often a mini path. Context, not the product.
- **Seeking Alpha:** Index strip (Dow, S&P, Nasdaq, oil, gold, BTC) above the story feed.
- **SIFT adopt:** Keep the CoinGecko crypto tape under the sticky stack. Rates stay a labeled “coming soon” slot with no invented yields.

## Typography

- **TradingView:** Compact sans for data; large display type only on marketing surfaces.
- **Koyfin / Finviz:** Dense tabular numerals, right-aligned money columns, muted labels.
- **Motley Fool / Seeking Alpha:** Strong headline hierarchy; body stays readable.
- **SIFT adopt:** One sans for UI (`IBM Plex Sans`), mono for figures (`IBM Plex Mono`). Serif remains only on long-form essays (QQQI). Letter-spacing and uppercase kickers for section labels.

## Putting top performers up front

- **Finviz:** Top gainers/losers before news.
- **Motley Fool:** Scoreboard and “top stocks” above articles.
- **TradingTheTrend:** Win-rate and trade-log headline before features/pricing.
- **Seeking Alpha:** Most-active / movers beside the feed.
- **SIFT adopt:** Compact brand hero → **Top Strategies** cards (best 5 by paper return) → full sortable table → Meme Coins CTA. Meme Coins page opens on open positions, closed trades, P&L, and win rate from `memescan/data/*`.

## Trust labels (keep)

- As-of stamps, paper-only disclaimers, early-window flags, and source links stay visible. Empty modules say “coming soon” with no fake figures. Site stays anonymous.
