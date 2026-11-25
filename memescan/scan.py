"""Pull public Solana candidates. v2 feed: boost, profile, and new pairs. Cap 60."""

import time
from datetime import timedelta

import plan
import public_http
import store
from audit import fetch_pairs, iso, open_cards, parse_time, snapshot, utc_now

LISTS = (
    ("boost", "https://api.dexscreener.com/token-boosts/top/v1"),
    ("boost", "https://api.dexscreener.com/token-boosts/latest/v1"),
    ("profile", "https://api.dexscreener.com/token-profiles/latest/v1"),
    ("profile", "https://api.dexscreener.com/token-profiles/recent-updates/v1"),
)
# Public search responses include pairCreatedAt. pumpswap and raydium are the
# queries whose Solana hits are actually new pairs; a bare SOL search is not.
NEW_PAIR_SEARCHES = (
    "https://api.dexscreener.com/latest/dex/search?q=pumpswap",
    "https://api.dexscreener.com/latest/dex/search?q=raydium",
)


def merge_feed_rows(rows):
    """One candidate per mint. Every feed that named it is kept."""
    merged = {}
    for row in rows:
        mint = row.get("mint")
        if not mint:
            continue
        feed = row.get("feed")
        if mint not in merged:
            copied = dict(row)
            copied["sources"] = []
            merged[mint] = copied
        slot = merged[mint]
        if feed and feed not in slot["sources"]:
            slot["sources"].append(feed)
        current_liq = slot.get("liquidity_usd")
        new_liq = row.get("liquidity_usd")
        if new_liq is not None and (current_liq is None or new_liq > current_liq):
            sources = slot["sources"]
            slot.clear()
            slot.update(row)
            slot["sources"] = sources
    result = []
    for slot in merged.values():
        feeds = slot.get("sources") or []
        slot["source"] = feeds[0] if len(feeds) == 1 else ",".join(feeds)
        result.append(slot)
    return result


def take_newest(rows, cap):
    def created(row):
        value = row.get("pair_created_at")
        if isinstance(value, (int, float)):
            return value
        moment = parse_time(value)
        return moment.timestamp() if moment else 0

    ordered = sorted(rows, key=created, reverse=True)
    return ordered[:cap]


def _collect_lists():
    found = []
    errors = []
    for feed, url in LISTS:
        try:
            payload = public_http.fetch_json(url, timeout=30)
        except public_http.SourceUnavailable as err:
            errors.append("%s: %s" % (feed, err))
            continue
        rows = payload if isinstance(payload, list) else []
        for row in rows:
            if not isinstance(row, dict) or row.get("chainId") != "solana":
                continue
            mint = row.get("tokenAddress")
            if not mint:
                continue
            found.append({
                "mint": mint,
                "feed": feed,
                "list_url": url,
                "description": row.get("description") or "",
                "page_url": row.get("url") or "",
            })
        time.sleep(0.4)
    return found, errors


def _collect_new_pairs():
    found = []
    errors = []
    for url in NEW_PAIR_SEARCHES:
        try:
            payload = public_http.fetch_json(url, timeout=30)
        except public_http.SourceUnavailable as err:
            errors.append("new_pairs: %s" % err)
            continue
        pairs = payload if isinstance(payload, list) else (payload or {}).get("pairs") or []
        for pair in pairs:
            if not isinstance(pair, dict) or pair.get("chainId") != "solana":
                continue
            if pair.get("pairCreatedAt") in (None, ""):
                continue
            mint = ((pair.get("baseToken") or {}).get("address"))
            if not mint:
                continue
            found.append({
                "mint": mint,
                "feed": "new_pairs",
                "list_url": url,
                "description": "",
                "page_url": pair.get("url") or "",
                "pair": pair,
            })
        time.sleep(0.4)
    return found, errors


def _liquidity(pair):
    raw = ((pair.get("liquidity") or {}).get("usd"))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _age_ok(pair, now):
    created = parse_time(pair.get("pairCreatedAt"))
    if created is None:
        return False
    age = (now - created).total_seconds()
    return 0 <= age <= plan.MAX_AGE_S


def _candidate_from_pair(meta, pair):
    liquidity = _liquidity(pair)
    base = pair.get("baseToken") or {}
    info = pair.get("info") or {}
    websites = [site.get("url") for site in (info.get("websites") or []) if isinstance(site, dict) and site.get("url")]
    socials = info.get("socials") if isinstance(info.get("socials"), list) else []
    m5 = ((pair.get("txns") or {}).get("m5")) or {}
    return {
        "mint": meta["mint"],
        "feed": meta.get("feed"),
        "list_url": meta.get("list_url"),
        "description": meta.get("description") or "",
        "page_url": pair.get("url") or meta.get("page_url") or "",
        "symbol": base.get("symbol") or "",
        "name": base.get("name") or "",
        "websites": websites,
        "socials": socials,
        "pair_address": pair.get("pairAddress"),
        "dex_id": pair.get("dexId"),
        "price_usd": pair.get("priceUsd"),
        "liquidity_usd": liquidity,
        "pair_created_at": pair.get("pairCreatedAt"),
        "volume_h1": (pair.get("volume") or {}).get("h1"),
        "txns_m5": {"buys": m5.get("buys"), "sells": m5.get("sells")},
    }


def main():
    now = utc_now()
    run_id = iso(now)
    listed, list_errors = _collect_lists()
    searched, search_errors = _collect_new_pairs()
    errors = list_errors + search_errors
    if not listed and not searched and errors:
        print("memescan scan: list APIs down (%s). Skipping run." % "; ".join(errors))
        store.write_json("latest_run.json", {"run_id": run_id, "count": 0, "skipped": True, "errors": errors, "rule_version": "v2"})
        return 0
    need = []
    seen_need = set()
    for item in listed:
        if item["mint"] not in seen_need:
            seen_need.add(item["mint"])
            need.append(item["mint"])
    pairs = {}
    try:
        for start in range(0, len(need), 20):
            pairs.update(fetch_pairs(need[start:start + 20]))
            time.sleep(0.3)
    except public_http.SourceUnavailable as err:
        print("memescan scan: pair lookup down (%s). Skipping run." % err)
        store.write_json("latest_run.json", {"run_id": run_id, "count": 0, "skipped": True, "errors": [str(err)], "rule_version": "v2"})
        return 0
    built = []
    for item in listed:
        pair = pairs.get(item["mint"])
        if not pair or not _age_ok(pair, now):
            continue
        liquidity = _liquidity(pair)
        if liquidity is None or liquidity < plan.LIQUIDITY_FAIL:
            continue
        built.append(_candidate_from_pair(item, pair))
    for item in searched:
        pair = item.get("pair") or {}
        if not _age_ok(pair, now):
            continue
        liquidity = _liquidity(pair)
        if liquidity is None or liquidity < plan.LIQUIDITY_FAIL:
            continue
        built.append(_candidate_from_pair(item, pair))
    kept = take_newest(merge_feed_rows(built), plan.CANDIDATE_CAP_V2)
    counts = {"boost": 0, "profile": 0, "new_pairs": 0}
    for row in kept:
        record = {
            "run_id": run_id,
            "rule_version": "v2",
            "fetched_at": iso(now),
            "feed": row.get("feed"),
            "source": row.get("source"),
            "sources": row.get("sources") or [],
            "list_url": row.get("list_url"),
            "mint": row.get("mint"),
            "symbol": row.get("symbol") or "",
            "name": row.get("name") or "",
            "description": row.get("description") or "",
            "websites": row.get("websites") or [],
            "socials": row.get("socials") or [],
            "pair_address": row.get("pair_address"),
            "dex_id": row.get("dex_id"),
            "url": row.get("page_url") or "",
            "price_usd": row.get("price_usd"),
            "liquidity_usd": row.get("liquidity_usd"),
            "pair_created_at": row.get("pair_created_at"),
            "volume_h1": row.get("volume_h1"),
            "txns_m5": row.get("txns_m5") or {},
        }
        store.append_jsonl("candidates.jsonl", record)
        for feed in record["sources"]:
            if feed in counts:
                counts[feed] += 1
        try:
            snapshot(record["mint"], float(record["price_usd"]), record.get("list_url") or "dexscreener", now)
        except (TypeError, ValueError):
            pass
    extra = []
    kept_mints = {row.get("mint") for row in kept}
    for card in open_cards():
        opened = parse_time(card.get("t0"))
        if opened is None:
            continue
        if now - opened > timedelta(hours=26):
            continue
        if card.get("mint") and card.get("mint") not in kept_mints:
            extra.append(card["mint"])
    if extra:
        from grade import refresh_prices
        refresh_prices(extra[:30])
    store.write_json("latest_run.json", {
        "run_id": run_id,
        "rule_version": "v2",
        "count": len(kept),
        "by_source": counts,
        "skipped": False,
        "errors": errors,
        "fetched_at": iso(now),
    })
    print("memescan scan v2: %s candidates (cap %s). by source %s" % (len(kept), plan.CANDIDATE_CAP_V2, counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
