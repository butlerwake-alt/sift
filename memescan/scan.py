"""Pull public Solana candidates. Paper list only. Cap 30."""

import time
from datetime import timedelta

import plan
import public_http
import store
from audit import fetch_pairs, iso, open_cards, parse_time, snapshot, utc_now

LISTS = (
    ("boost_top", "https://api.dexscreener.com/token-boosts/top/v1"),
    ("boost_latest", "https://api.dexscreener.com/token-boosts/latest/v1"),
    ("profile_latest", "https://api.dexscreener.com/token-profiles/latest/v1"),
)


def _collect_addresses():
    ordered = []
    seen = set()
    sources = {}
    errors = []
    for name, url in LISTS:
        try:
            payload = public_http.fetch_json(url, timeout=30)
        except public_http.SourceUnavailable as err:
            errors.append("%s: %s" % (name, err))
            continue
        rows = payload if isinstance(payload, list) else []
        for row in rows:
            if not isinstance(row, dict) or row.get("chainId") != "solana":
                continue
            mint = row.get("tokenAddress")
            if not mint or mint in seen:
                continue
            seen.add(mint)
            ordered.append(mint)
            sources[mint] = {
                "list": name,
                "source": url,
                "description": row.get("description") or "",
                "url": row.get("url") or "",
            }
        time.sleep(0.4)
    return ordered, sources, errors


def _age_ok(pair, now):
    created = parse_time(pair.get("pairCreatedAt"))
    if created is None:
        return False
    age = (now - created).total_seconds()
    return 0 <= age <= plan.MAX_AGE_S


def _liquidity(pair):
    raw = ((pair.get("liquidity") or {}).get("usd"))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def main():
    now = utc_now()
    run_id = iso(now)
    mints, sources, errors = _collect_addresses()
    if not mints and errors:
        print("memescan scan: list APIs down (%s). Skipping run." % "; ".join(errors))
        store.write_json("latest_run.json", {"run_id": run_id, "count": 0, "skipped": True, "errors": errors})
        return 0
    pairs = {}
    try:
        for start in range(0, len(mints), 20):
            pairs.update(fetch_pairs(mints[start:start + 20]))
            time.sleep(0.3)
    except public_http.SourceUnavailable as err:
        print("memescan scan: pair lookup down (%s). Skipping run." % err)
        store.write_json("latest_run.json", {"run_id": run_id, "count": 0, "skipped": True, "errors": [str(err)]})
        return 0
    kept = []
    for mint in mints:
        pair = pairs.get(mint)
        if not pair:
            continue
        liquidity = _liquidity(pair)
        if liquidity is None or liquidity < plan.LIQUIDITY_FAIL:
            continue
        if not _age_ok(pair, now):
            continue
        kept.append((mint, pair, liquidity))
        if len(kept) >= plan.CANDIDATE_CAP:
            break
    for mint, pair, liquidity in kept:
        meta = sources.get(mint) or {}
        base = pair.get("baseToken") or {}
        info = pair.get("info") or {}
        websites = [site.get("url") for site in (info.get("websites") or []) if isinstance(site, dict) and site.get("url")]
        socials = info.get("socials") if isinstance(info.get("socials"), list) else []
        m5 = ((pair.get("txns") or {}).get("m5")) or {}
        row = {
            "run_id": run_id,
            "fetched_at": iso(now),
            "list": meta.get("list"),
            "source": meta.get("source"),
            "mint": mint,
            "symbol": base.get("symbol") or "",
            "name": base.get("name") or "",
            "description": meta.get("description") or "",
            "websites": websites,
            "socials": socials,
            "pair_address": pair.get("pairAddress"),
            "dex_id": pair.get("dexId"),
            "url": pair.get("url") or meta.get("url") or "",
            "price_usd": pair.get("priceUsd"),
            "liquidity_usd": liquidity,
            "pair_created_at": pair.get("pairCreatedAt"),
            "volume_h1": (pair.get("volume") or {}).get("h1"),
            "txns_m5": {"buys": m5.get("buys"), "sells": m5.get("sells")},
        }
        store.append_jsonl("candidates.jsonl", row)
        try:
            snapshot(mint, float(pair["priceUsd"]), meta.get("source") or "dexscreener", now)
        except (TypeError, ValueError, KeyError):
            pass
    extra = []
    for card in open_cards():
        opened = parse_time(card.get("t0"))
        if opened is None:
            continue
        if now - opened > timedelta(hours=26):
            continue
        if card.get("mint") and card.get("mint") not in {mint for mint, _pair, _liq in kept}:
            extra.append(card["mint"])
    if extra:
        from grade import refresh_prices
        refresh_prices(extra[:30])
    store.write_json("latest_run.json", {
        "run_id": run_id,
        "count": len(kept),
        "skipped": False,
        "errors": errors,
        "fetched_at": iso(now),
    })
    print("memescan scan: %s candidates (cap %s)." % (len(kept), plan.CANDIDATE_CAP))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
