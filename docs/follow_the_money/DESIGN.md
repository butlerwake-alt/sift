# Follow the Money — technical design

Status of this document: design for a proposed SIFT module. Section 8 of `SPEC.md` governs. This PR does not fetch filings, does not run a backtest, and does not deploy. The public page is a Phase 1–2 preview rendered only from `data/follow_money.json`. Every row in that file is marked `sample: true` and is not a filing, a holding, or a performance result.

> **Update (Nov 2026, owner request):** `tools/follow_money.py` now fetches real public data daily (House Clerk PTRs, SEC Form 4 code P, SEC 13F-HR for a curated manager list, CoinGecko public-treasury data) into the same schema-1 JSON, with `sample: false`, a `source_url`, `sector`, `copy_line`, and `csv` on every real row, plus `stale`, `as_of`, `retrieved_at`, and `note` per section. Senate eFD, whale wallets, ETF flows, and social accounts are not connected; social shows "coming soon". Still research only: no orders, no backtest numbers.

The module is research-only. It must not place orders, connect a wallet, or present a disclosure as a trade to copy for profit.

## 1. What this PR ships

| Piece | Role |
| --- | --- |
| `docs/follow_the_money/SPEC.md` | Owner concept spec, unchanged. |
| `docs/follow_the_money/DESIGN.md` | This design. |
| `data/follow_money.json` | Static sample feed. Schema below. No live figures. |
| `follow_money.html`, `follow_money.js` | Preview dashboard. Reads the JSON file with `fetch` on the same origin. No other network calls. |
| `tools/follow_money.py` | Offline stub. Validates the JSON shape and prints the source inventory. No sockets. |
| Home-page callout and shared nav/footer link | Entry points. The page is labeled Preview, coming soon. |

Out of scope until a later, separately approved phase: ingestion, raw-file storage, identity resolution, scoring, backtests, alerts, and any number that claims a return.

## 2. Technical design

### 2.1 Boundaries

- Presentation and a local JSON file only, in this phase. `build_data.py`, `publish.sh`, `data.js`, `history.json`, and the existing files under `data/` and `tools/` stay untouched.
- The page never computes a return. It refuses to render a backtest block. The JSON schema has no return fields.
- A follow list is stored in `localStorage` under `sift.followMoney.v1`. It is a set of sample entity ids on this browser. It is not an account, not synced, and not sent anywhere.
- “Copy the list (research only)” writes plain text: a research-only banner, the section’s disclosure lag, and the tickers on the sample cards. It does not build an order.

### 2.2 Later pipeline (not built)

When the owner approves ingestion, the pipeline is four stores, all append-only:

1. **Raw.** Bytes of the filing or page, the source URL, the retrieval timestamp, and a content hash. Never rewritten.
2. **Normalized record.** One row per disclosed fact after parse: who, instrument, action, amount or range, trade/as-of date, public filing date, amendment link. Parser version stored on the row.
3. **Usable clock.** `usable_at = public_date + processing_delay`. Research code may read a record only at `usable_at`. Nothing in a backtest may use `trade_date` as if the public already knew it.
4. **Published snapshot.** The JSON the site renders, built only from normalized rows whose `usable_at` has passed, with the coverage report (what was fetched, what failed, what is still late).

Facts, calculated signals, hypotheses, and editorial notes are separate fields. A card on the site may show a fact without a signal. It may not show a signal that does not point at a fact and a primary URL.

Ambiguous parses (unknown ticker, insider vs trust, amendment that contradicts the prior filing) are quarantined and do not appear on the public page.

Identity resolution (a member, a filer CIK, a fund, a wallet label) is a table of ids with source evidence. The preview uses the literal string on the sample card and does not guess.

### 2.3 Page model

Desktop: a single feed. A coverage box, then one section per stream, each with source, lag, entity groups, and explainable cards.

Phone (max-width 768px): the same feed as accordion cards, closed by default, one section open at a time. A card shows a title and a one-line summary. Opening a section reveals entity rows; one signal card is open at a time. State is the URL hash (`#congress`, `#funds`, and so on).

Each signal card, when real data exists, answers:

- Who
- What (instrument and action)
- When it became public (publication date, distinct from the trade date)
- Why it is in this stream
- Confidence (unset until a scoring phase exists)
- Caveats, including the lag

The preview fills those slots with sample text and a Sample chip. Confidence is “Not scored.”

## 3. Public-source inventory

No source below is called by this PR. Access terms are the publisher’s, and they change. A future ingester has to re-read the terms before the first request and send a descriptive User-Agent where the publisher requires one. Rate limits below are the published ones as of this design, not a guess at what an unofficial mirror allows.

### 3.1 Congress — STOCK Act periodic transaction reports

| | |
| --- | --- |
| House | [disclosures-clerk.house.gov](https://disclosures-clerk.house.gov/FinancialDisclosure). Periodic transaction reports. Public HTML and PDF. No documented bulk API and no API key. |
| Senate | [efdsearch.senate.gov](https://efdsearch.senate.gov/). Electronic financial disclosure search. The site presents a usage agreement in the browser. It is not a public bulk API. |
| What a record contains | Member, asset, transaction type, amount range (not an exact size), transaction date, filing date. |
| Lag | A periodic transaction report is due within 30 days after the filer is notified of the transaction, and in no case later than 45 days after the transaction. That is the statutory window, not a real-time feed. |
| Access | Public pages. Polite retrieval only, after the owner approves and after the Senate agreement is reviewed. No published requests-per-second number. Design cap until then: well under one request per second per host, with backoff, and no parallel crawls. |
| Do not | Circumvent the Senate agreement, scrape personal contact data, or treat a PDF range as an exact dollar amount. |

### 3.2 Institutional holdings — SEC Form 13F

| | |
| --- | --- |
| Source | SEC EDGAR. [EDGAR access guidance](https://www.sec.gov/os/accessing-edgar-data). Filings are Form 13F-HR and amendments. Bulk and per-CIK JSON live on `data.sec.gov` and `www.sec.gov`. |
| Who files | Institutional investment managers over the statutory threshold (currently $100 million). Examples of the kind of filer this section is for: large public managers such as Berkshire Hathaway, Pershing Square, ARK, and Bridgewater. The sample file does not contain their holdings. |
| What a record contains | CUSIP or ticker, shares or principal, value, and the manager. A 13F is a quarter-end snapshot of long U.S.-listed positions, not a list of trades and not short positions. |
| Lag | Due within 45 days after the calendar quarter ends. The holding date is the quarter end. The public date is the filing timestamp. “Change vs last quarter” is the difference between two filings, which can both be weeks old. |
| Access | SEC fair-access policy: no more than 10 requests per second, and a User-Agent that identifies the operator. Declared `Accept` headers as the SEC documents them. Respect 403/429 and stop. |
| Do not | Present 13F value as a buy or sell that happened on a particular day. Do not fill missing tickers by guessing. |

### 3.3 Insiders — SEC Form 4, open-market buys only

| | |
| --- | --- |
| Source | EDGAR Form 4 (and amendments). Same access policy as 13F: 10 requests per second, descriptive User-Agent. |
| Lag | Form 4 is due within two business days of the transaction. That is still not real time, and the research clock adds a processing delay on top (section 4). |
| Split that must be preserved | Open-market purchases (transaction code **P**) are the only rows this stream shows. Grants and awards (code **A**), option exercises (code **M**), and sales (code **S**) are different facts. A 10b5-1 plan is flagged on the form (the plan checkbox and footnotes), not inferred. Those buckets get their own stores later. They are not labeled as discretionary buys. The preview section states this split and contains no grant and no plan row. |
| What a record contains | Issuer, reporting owner, relationship, security, code, shares, price, value if stated, transaction date, filing date, footnote text. |

### 3.4 Crypto treasuries and labeled large wallets

| | |
| --- | --- |
| Corporate treasuries | Company disclosures: 8-K, 10-Q, 10-K, and earnings releases filed or linked from the company’s own investor page. EDGAR covers the SEC filers. Same 10-request EDGAR cap. |
| Spot ETF holdings | The sponsor’s public holdings or basket file (the issuer’s site). Each issuer has its own terms. Many allow viewing and forbid resale or automated collection. No ingestion until the owner approves a specific issuer and its terms. |
| On-chain wallets | Only addresses a public document already labels (an issuer transparency page, a company’s filing, or an explorer label that cites a public source). Unlabeled addresses are not “whales” and are not assigned to a person. |
| Explorers | Public APIs (for example a mempool or an execution-layer client’s documented API) have their own keys and rate limits. Those limits are read from that provider at build time. This design does not pick a provider and does not ship a key. |
| What this stream is not | A rumor about a partnership is not treasury demand. The spec separates token demand from announcement copy. The preview has no announcement cards. |

### 3.5 Verified social accounts

A later top-10 list is allowed only for accounts whose calls or holdings are checkable against a primary source: a public filing, a published portfolio, or a wallet address the account itself has published and that matches section 3.4. Engagement, follower counts, and screenshots are not verification.

This preview does not name real accounts and does not rank anyone. The sample card shows the fields a verified row would need. The section copy says the top-10 list is not filled.

### 3.6 Source registry (future table)

Each source row, when ingestion exists: `source_id`, publisher, base URL, terms URL, robots or fair-access note, max requests per second, User-Agent requirement, last review date, enabled flag (default off). The stub prints this inventory. It does not set `enabled`.

## 4. Timestamp model

Three dates are never collapsed into one.

| Field | Meaning |
| --- | --- |
| `trade_date` or `as_of_date` | When the economic event happened, as the form states it. For a 13F this is the quarter-end holding date, not a trade. For a Form 4 or a congressional PTR it is the transaction date. |
| `public_date` | When the filing or page first became public (acceptance datetime on EDGAR, or the posting date on a clerk site). Amendments keep their own `public_date` and point at the prior accession. |
| `retrieved_at` | When SIFT stored the raw bytes. This is not a market timestamp. |
| `usable_at` | `public_date` plus a predeclared processing delay. Backtests and any “what was knowable” UI may use the record only at `usable_at`. |

Processing delay, to be frozen in writing before any backtest and not tuned after seeing results:

- EDGAR filings: the next regular U.S. equity session close after `public_date`, or one business day, whichever the pre-registration picks. Not zero.
- Congressional PDFs: one business day after `public_date`, and longer if the parse was quarantined.
- Issuer holdings pages: the timestamp printed on the file plus one calendar day, unless the file itself is already a prior-day report.

Rules:

- `trade_date` may be weeks before `public_date`. Entering a backtest on `trade_date` is lookahead and is a failed test.
- If `public_date` is missing, the record is not usable.
- A sample row uses the literal string `"sample"` for both dates so the UI cannot format it as a real day.
- The card shows the publication date as its own label (“Public: …”), not mixed into the headline.

Disclosure lag text is stored on the section and copied with any ticker list. Congress and 13F copy state the 45-day statutory outer window. Form 4 states two business days plus processing delay. Crypto and social state that the figure is only as fresh as the cited page.

## 5. Data schema (`data/follow_money.json`)

Schema version 1. `tools/follow_money.py` checks this shape. Encoding is UTF-8 JSON, no comments.

Top level:

| Field | Type | Required |
| --- | --- | --- |
| `schema` | number, must be `1` | yes |
| `preview` | boolean, `true` while no live feed is connected | yes |
| `phase` | string, `"1-2"` for this preview | yes |
| `status` | string, includes “Preview, coming soon” | yes |
| `sample_only` | boolean. When `true`, every card must have `sample: true` | yes |
| `disclaimer` | string | yes |
| `coverage` | object: `retrieved_at` (null or ISO), `publication_label`, `freshness`, `gaps` (string array) | yes |
| `sections` | array of section objects | yes |

Section:

| Field | Type | Required |
| --- | --- | --- |
| `id` | string, one of `congress`, `funds`, `insiders`, `crypto`, `social` | yes |
| `title` | string | yes |
| `summary` | one line for the closed accordion | yes |
| `blurb` | string, what the stream is and what it excludes | yes |
| `source_name` | string | yes |
| `source_url` | absolute `https` URL | yes |
| `as_of_label` | string, name of the event date (“Trade date”, “Quarter-end”, …) | yes |
| `public_label` | string, name of the publication date | yes |
| `lag` | string, the delay a reader must see before copying tickers | yes |
| `cards` | array | yes |

Card:

| Field | Type | Required |
| --- | --- | --- |
| `id` | string, unique in the file | yes |
| `sample` | boolean | yes |
| `entity` | string, grouping key shown as the entity heading | yes |
| `who` | string | yes |
| `what` | string, instrument. Samples use `SAMPLE` | yes |
| `action` | string | yes |
| `detail` | string, amount, weight, role, or verification. No invented live figure | yes |
| `trade_date` | string. Samples use `sample` | yes |
| `public_date` | string. Samples use `sample` | yes |
| `why` | string | yes |
| `confidence` | string. Samples use a not-scored sentence | yes |
| `caveats` | string | yes |
| `tickers` | array of strings. Samples use `["SAMPLE"]` | yes |
| `weights` | array of strings, parallel to tickers or empty. Samples use `[]` so a weight is not fabricated | yes |

There is no field for return, CAGR, win rate, or backtest output. Adding one is a schema change that waits for Phase 3 and a real run.

The follow-list record in `localStorage` is `{ "id": "<entity slug>", "label": "<entity>", "section": "<section id>" }`. It is derived from cards already on the page.

## 6. Regime definitions

These are predeclared for a future test. They are not computed, not shown as gauges on the Follow the Money page, and not fitted to a result. They are a different question from the existing SIFT board regimes (`trend_up`, `range`, `risk_off`, `trend_down`, `shock`), which stay the board’s labels. A later study may report both, but it may not rename one as the other after seeing returns.

Benchmark for equities: SPY. For bitcoin: BTC spot daily close from the same vendor the study pre-registers. Thresholds use only information available at the close of day T, and a day is labeled for use on day T+1.

| Regime | Rule, evaluated on the prior close |
| --- | --- |
| Bull | Close above the 200-day simple average and the 63-day total return is positive. |
| Bear | Close below the 200-day simple average and the 63-day total return is negative. |
| Sideways | Neither bull nor bear, and the absolute 63-day total return is under 5%. |
| High-vol | 20-day realized volatility of daily returns is above the 252-day median of that same 20-day measure. High-vol can overlap bull, bear, or sideways. It is a flag, not a fourth mutually exclusive bucket. If a day is none of bull, bear, or sideways, it is recorded as `unclassified` and excluded from regime splits rather than forced into one. |

A study that wants different windows writes a new version id. It does not edit these numbers in place.

## 7. Backtest methodology

Not run. No output numbers exist, and the page must not display any. This section is the procedure a later Phase 3 lab would have to follow. It is not permission to run it.

Question the spec allows, each as its own pre-registered test, reported even when the result is flat or negative:

- Congressional disclosures, entered only at `usable_at`, held for a pre-registered horizon.
- Form 4 code P only, same clock. Grants, exercises, and 10b5-1 rows are not mixed in.
- 13F accumulation: change versus the prior filing, entered at `usable_at` of the later filing.
- Cross-source clusters: two or more independent sources whose usable windows overlap on the same instrument. Independence is pre-registered (a fund and its own social account are one source).
- Benchmarks: SPY, BTC, a top-5 liquid crypto basket defined before the run, and the single name itself.

Entry and exit:

- Signal available at `usable_at`. Fill at the next bar’s close after that, with a pre-registered cost (equities and crypto costs written down before the run, not taken from the winning variant).
- No fill on `trade_date`.
- Delisted names stay in the book through the delisting return. Survivorship by “today’s members only” is reported as a bias, as on the existing board.
- Amendments: the position uses the amended fact only from the amendment’s own `usable_at`. The original fact stands until then.

Metrics, each versus the pre-registered benchmark: cumulative return, annualized return, max drawdown, volatility, win rate, trade count, turnover. Plus a minimum sample size below which the study prints “not enough events” instead of a ratio.

Robustness, required before a result can be called anything but exploratory: one walk-forward split declared first, a cost sensitivity, a delay sensitivity (processing delay doubled), and a note when the universe is a current constituent list.

Negative and inconclusive results are published in the same table as positive ones. A high historical return is not evidence the signal will work, and the write-up has to say that in the same view as the number.

## 8. Test plan

Automated now (the stub, plus a browser check of the preview):

- `python3 tools/follow_money.py` exits 0, prints sources, and rejects a missing required field. It does not open a socket. `--fetch` exits non-zero and still does not open a socket.
- With `sample_only: true`, a card without `sample: true` fails the stub.
- The JSON has no return-like keys (`cagr`, `return_pct`, `sharpe`, `backtest`).
- The page shows “Preview, coming soon”, the disclaimer at top and bottom, a coverage box, and Sample on every card.
- Copy text includes “Research only” and the section lag, and does not include a performance figure.
- Follow toggles write only `localStorage`.
- At 390px the Follow the Money page, the home page, and a strategy page do not scroll horizontally. Home and the preview open as closed accordions.
- Console on those pages has no errors from first-party scripts. A failed public price quote on the home ticker may leave the last good row or the fallback line; it must not throw.

Before any live row is published, add:

- Timestamp ordering: `trade_date <= public_date <= usable_at`, and a fixture that fails if a backtest fill is dated before `usable_at`.
- Parser fixtures from saved raw files (a PTR, a 13F information table, a Form 4 with code P, a Form 4 with code A, a Form 4 with the 10b5-1 box). Code A must not land in the open-market list.
- Amendment fixture: the amended share count is invisible before the amendment’s `usable_at`.
- Quarantine fixture: missing ticker or missing `public_date` does not render.
- Coverage fixture: a failed fetch appears in `gaps` and does not look like an empty market.

## 9. Staged phases

| Phase | Spec name | This PR | Later, only with owner approval |
| --- | --- | --- | --- |
| 1 | Evidence foundation | Schema, source inventory, lag and timestamp model, offline stub, sample JSON | Raw store, parsers, source registry with `enabled` still default off |
| 2 | Research dashboard | Preview shell: feed, cards, entity groups, coverage box, local follow list, research-only copy | Replace sample cards with normalized rows. Still no returns |
| 3 | Backtest lab | Not started. No numbers on the page | Pre-register one test, run it, publish the negative result the same way as a positive one |
| 4 | Validation | Not started | Walk-forward, cost and delay sensitivity, minimum sample, outside review |

The preview may stay on the site as sample data. It must keep the Sample chip and the coming-soon line until Phase 2 replaces those cards with stored filings. Removing the chip is a schema failure (`sample_only` would be false, and every remaining card still needs `sample` or a real source URL and a real `public_date`).

## 10. Legal, API, and product limits

- Not legal, investment, or tax advice. The page says so at the top and the bottom. Copying a disclosed holding is not the same as copying the result, because of lag, ranges instead of exact size, and everything the form does not show.
- EDGAR: 10 requests per second and a descriptive User-Agent, per the SEC’s current fair-access page. That is a hard cap for any future client.
- Senate eFD: no bulk API. The site agreement has to be read before automation. If the agreement forbids automated collection, the Senate stream stays manual.
- House clerk: public pages, no documented API. Same politeness rule. PDFs can be image-only; a failed parse is a gap, not a zero.
- Issuer holdings pages and explorer APIs: terms and rate limits differ, and several forbid redistribution. No key is stored in the repo.
- Do not deanonymize wallets. Do not attach a person to an address the person or a filing has not already published.
- Do not mix Form 4 grants, exercises, or 10b5-1 plan transactions into the open-market buy list.
- 13F omits shorts, many non-U.S. holdings, and everything under the reporting threshold. A “top holding” is top of the filed long book only.
- Congressional amounts are ranges. Do not invent a midpoint and call it the trade size in the UI. A later study that needs a midpoint says it is a midpoint assumption.
- No brokerage connection, no wallet connection, no order ticket, no alert that tells someone to buy. The follow list is a local research bookmark.
- Nothing here is real time. The oldest statutory clocks are 45 days (Congress outer bound, 13F) plus the processing delay.

## 11. Missing inputs (blocked)

The preview is honest about these. They are why every card says Sample.

- No House or Senate feed connected, and no decision on whether Senate automation is allowed.
- No EDGAR User-Agent identity approved for this repo, and no ingestion schedule.
- No CIK map, no member-id map, no ticker crosswalk from CUSIP.
- No saved raw filings to parse.
- No chosen processing-delay version id (the candidates are in section 4; none is frozen).
- No crypto issuer terms review, and no allow-list of labeled wallets.
- No social account that meets the verification rule.
- No pre-registered backtest, no cost schedule for this module, no benchmark vendor pin, no result file.
- No review queue or owner sign-off for publishing a non-sample row.

Until those exist, the page stays a preview and the stub stays offline.
