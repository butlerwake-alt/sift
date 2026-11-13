# Redesign research

Looked at Finviz, Koyfin, TradingView, Seeking Alpha, Motley Fool, Morningstar, Robinhood and Public marketing pages, Unusual Whales, and Quiver Quantitative. The useful pattern is not a shared color. It is how they make a lot of numbers feel trustworthy and easy to come back to.

## What those sites do

- **Dense tables, with air.** Finviz, Koyfin, and Quiver put the ranked list in a real table: one row per name, tabular figures, a sticky header, and sort on the column. They do not hide the list inside cards. Cards are for a second layer (a name, a filing, an idea), not for the ranking itself.
- **A tape at the top.** Finviz and TradingView open with a moving strip of live symbols, green for up and red for down, plus a small sparkline. The tape is context. It is not the product.
- **A pro palette, dark or light.** TradingView, Koyfin, Unusual Whales, and Quiver default to a near-black field, a blue-gray panel, and one accent. Morningstar, Seeking Alpha, and Public do the same hierarchy in light: white panels, a dark app bar, and the same green/red meaning. Green and red are reserved for up and down. They are not decoration.
- **A short hierarchy.** Public and Robinhood marketing pages lead with one sentence and one number. Motley Fool leads with the scoreboard, then the story. The page that works says what it is in a line, then shows the board.
- **Trust, labeled.** Morningstar separates the star rating from the analyst note and prints the as-of date. Seeking Alpha labels quant versus people. Motley Fool prints the track-record window next to the return. A figure without a window and a source looks like a promise.
- **Sparklines in the row.** TradingView watchlists and Finviz maps give each row a path so the eye can scan shape without opening a chart.
- **Sticky navigation.** The bar stays put. On a phone, a bottom tab bar (Robinhood, Public) keeps Home and the main list one tap away. Tap targets stay large.
- **Coming-soon is a slot, not a fake quote.** Unusual Whales and Quiver only print a flow or a yield when the feed is real. An empty module says so.

## What this redesign adopts

- A coin tape on top, then a single sticky bar (brand, sections, light/dark).
- The forward leaderboard is the first real module, with a sparkline column and a sticky header. Forward returns under 90 days are labeled **too early to tell**. The number stays, because it is a real mark. The label stops a six-day result from reading like a verdict.
- Top historical paths sit beside that table under a **BACKTEST** label, with the window and the drawdown. They are never mixed into the forward rank.
- Market mood is a one-line strip of the same regime already on the page, with the full dial lower down.
- A rates strip and a card grid reserve space for later modules. Each one says **coming soon** and has no figures.
- Phone behavior from the previous refresh stays: sections collapse, one open at a time, and a sticky bottom bar. Targets are at least 44px.
- Type is a plain system sans for the board. Serif stays on the long QQQI essay. No web-font request, no tracker.

## What was left alone

Every figure still comes from `data.js`, `history.json`, or `data/*.json`, or from the existing CoinGecko tape. Placeholder modules do not invent prices, yields, or returns. The hero line stays the everyday-resource sentence, plus the paper-results disclaimer. The site stays anonymous.
