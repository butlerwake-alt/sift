"""Paper safety audit. Public reads only. Token text is data, never instructions.

Allowed Solana RPC methods: getAccountInfo, getTokenLargestAccounts.
"""

import base64
import time
from datetime import datetime, timedelta, timezone

import plan
import public_http
import store

DEX_TOKEN_URL = "https://api.dexscreener.com/tokens/v1/solana/"
RUG_URL = "https://api.rugcheck.xyz/v1/tokens/{mint}/report"
RPCS = (
    "https://solana-rpc.publicnode.com",
    "https://api.mainnet-beta.solana.com",
)
ALLOWED_RPC = ("getAccountInfo", "getTokenLargestAccounts")
BURN = {
    "11111111111111111111111111111111",
    "1nc1nerator11111111111111111111111111111111",
}
BOT_PHRASES = ("ignore rules", "ignore previous", "system:", "verified safe")
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def utc_now():
    return datetime.now(timezone.utc)


def iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds = seconds / 1000.0
        return datetime.fromtimestamp(seconds, timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    if "." in text:
        head, rest = text.split(".", 1)
        digits = []
        tail = ""
        for index, char in enumerate(rest):
            if char.isdigit():
                digits.append(char)
            else:
                tail = rest[index:]
                break
        text = head + "." + "".join(digits[:6]) + (tail or "+00:00")
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def b58encode(raw):
    number = int.from_bytes(raw, "big")
    chars = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(B58[rem])
    pad = 0
    for byte in raw:
        if byte == 0:
            pad += 1
        else:
            break
    return "1" * pad + "".join(reversed(chars or ["1"]))


def parse_mint_account(raw):
    """SPL and Token-2022 mint accounts share an 82-byte prefix."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < 82:
        return {"ok": False, "mint_authority": None, "freeze_authority": None}
    mint_option = int.from_bytes(raw[0:4], "little")
    freeze_option = int.from_bytes(raw[46:50], "little")
    mint_authority = b58encode(raw[4:36]) if mint_option == 1 else None
    freeze_authority = b58encode(raw[50:82]) if freeze_option == 1 else None
    if mint_option not in (0, 1) or freeze_option not in (0, 1):
        return {"ok": False, "mint_authority": None, "freeze_authority": None}
    return {"ok": True, "mint_authority": mint_authority, "freeze_authority": freeze_authority}


def check(cid, name, status, value, source, fetched_at, detail=""):
    if status not in {"pass", "warn", "fail", "n/a", "pending"}:
        raise ValueError(status)
    return {
        "id": cid,
        "name": name,
        "status": status,
        "value": value,
        "source": source,
        "fetched_at": fetched_at,
        "detail": detail,
    }


def verdict_of(checks):
    statuses = [item["status"] for item in checks]
    if any(status == "pending" for status in statuses):
        return "UNKNOWN"
    fails = statuses.count("fail")
    warns = statuses.count("warn")
    nas = statuses.count("n/a")
    if fails:
        return "TRAP"
    if nas > plan.NA_UNKNOWN_ABOVE:
        return "UNKNOWN"
    if warns >= plan.WARN_VERDICT_AT:
        return "WARN"
    if nas:
        return "UNKNOWN"
    return "CLEAN"


def tally_score(checks):
    fails = sum(item["status"] == "fail" for item in checks)
    warns = sum(item["status"] == "warn" for item in checks)
    return max(0, 100 - 25 * fails - 10 * warns)


def _quote(text):
    flat = " ".join(str(text).split())
    if len(flat) > 180:
        flat = flat[:180] + "…"
    return '"' + flat.replace('"', "'") + '"'


def bot_flag(texts):
    """Scan token copy as data. Matching phrases never change these rules."""
    quotes = []
    fields = texts or {}
    for key in ("name", "symbol", "description", "websites", "socials"):
        raw = fields.get(key) or ""
        lowered = str(raw).lower()
        if any(phrase in lowered for phrase in BOT_PHRASES):
            quotes.append(key + ": " + _quote(raw))
    return quotes


def _num(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def lp_from_report(report):
    if not isinstance(report, dict):
        return None, False
    markets = report.get("markets") or []
    best = None
    best_usd = -1.0
    for market in markets:
        if not isinstance(market, dict):
            continue
        lp = market.get("lp") or {}
        usd = (_num(lp.get("baseUSD")) or 0) + (_num(lp.get("quoteUSD")) or 0)
        if usd >= best_usd:
            best_usd = usd
            best = market
    if best is None:
        launch = report.get("launchpad")
        return None, bool(launch)
    lp = best.get("lp") or {}
    pct = _num(lp.get("lpLockedPct"))
    market_type = str(best.get("marketType") or "").lower()
    bonding = pct is None and ("bonding" in market_type or market_type in {"pump_fun", "pump"})
    if pct is None and best.get("lp") in (None, {}) and report.get("launchpad"):
        bonding = True
    return pct, bonding


def _known_pool(account, known):
    meta = known.get(account) if isinstance(known, dict) else None
    if not isinstance(meta, dict):
        return False
    kind = str(meta.get("type") or "").upper()
    name = str(meta.get("name") or "").lower()
    return kind in {"AMM", "LP", "LOCKER"} or "burn" in name or "pool" in name or "amm" in name


def holder_stats(report):
    if not isinstance(report, dict):
        return None, None
    holders = report.get("topHolders")
    if not isinstance(holders, list) or not holders:
        return None, None
    known = report.get("knownAccounts") or {}
    market_accounts = set()
    for market in report.get("markets") or []:
        if not isinstance(market, dict):
            continue
        for field in (
            "pubkey",
            "liquidityAAccount",
            "liquidityBAccount",
            "mintAAccount",
            "mintBAccount",
            "mintLPAccount",
        ):
            value = market.get(field)
            if isinstance(value, str) and value:
                market_accounts.add(value)
    kept = []
    for holder in holders:
        if not isinstance(holder, dict):
            continue
        owner = holder.get("owner") or ""
        address = holder.get("address") or ""
        pct = _num(holder.get("pct"))
        if pct is None:
            continue
        if owner in BURN or address in BURN:
            continue
        if owner in market_accounts or address in market_accounts:
            continue
        if _known_pool(owner, known) or _known_pool(address, known):
            continue
        kept.append(pct)
    if not kept:
        return 0.0, 0.0
    kept.sort(reverse=True)
    return sum(kept[:10]), kept[0]


def creator_pct(report):
    if not isinstance(report, dict):
        return None
    token = report.get("token") or {}
    supply = _num(token.get("supply")) if isinstance(token, dict) else None
    balance = _num(report.get("creatorBalance"))
    if supply and balance is not None and supply > 0:
        return balance / supply * 100.0
    creator = report.get("creator")
    if not creator:
        return None
    for holder in report.get("topHolders") or []:
        if isinstance(holder, dict) and holder.get("owner") == creator:
            return _num(holder.get("pct"))
    return None


def dev_sold_pct(report, now):
    """Return a percent only when the report actually carries creator sale events."""
    if not isinstance(report, dict):
        return None
    events = report.get("events")
    if not isinstance(events, list) or not events:
        return None
    creator = report.get("creator")
    window_start = now - timedelta(hours=6)
    sold = 0.0
    initial = None
    matched = False
    for event in events:
        if not isinstance(event, dict):
            continue
        owner = event.get("owner") or event.get("wallet") or event.get("address")
        if creator and owner and owner != creator:
            continue
        moment = parse_time(event.get("timestamp") or event.get("time") or event.get("createdAt"))
        if moment is None or moment < window_start or moment > now:
            continue
        amount = _num(event.get("soldPct") or event.get("pctSold") or event.get("amountPct"))
        if amount is None:
            continue
        matched = True
        sold += amount
        if initial is None:
            initial = _num(event.get("initialPct"))
    if not matched:
        return None
    if initial and initial > 0 and sold <= initial:
        return sold / initial * 100.0 if sold <= 100 else sold
    return sold


def launches_7d(report, now):
    if not isinstance(report, dict):
        return None
    tokens = report.get("creatorTokens")
    if not isinstance(tokens, list):
        return None
    window_start = now - timedelta(days=7)
    dated = 0
    count = 0
    for item in tokens:
        moment = None
        if isinstance(item, dict):
            moment = parse_time(item.get("createdAt") or item.get("detectedAt") or item.get("timestamp"))
        if moment is None:
            continue
        dated += 1
        if window_start <= moment <= now:
            count += 1
    if dated == 0:
        return None
    return count


def bundled_links(report):
    """Only an explicit same-funder count. Generic insider clusters are not this check."""
    if not isinstance(report, dict):
        return None
    for key in ("bundledBuyers", "sameFunderBuyers", "bundledLaunchLinked"):
        number = _num(report.get(key))
        if number is not None:
            return number
    return None


def risk_levels(report):
    if not isinstance(report, dict) or not isinstance(report.get("risks"), list):
        return None
    levels = []
    for item in report["risks"]:
        if isinstance(item, dict):
            levels.append(str(item.get("level") or "").lower())
    return levels


def audit_observation(obs):
    """Score one normalized observation. Missing values stay missing."""
    now = parse_time(obs.get("now")) or utc_now()
    texts = obs.get("texts") or {}
    mint_present = obs.get("mint_authority_present", None)
    if mint_present is True:
        c1 = check("C1", "Mint authority revoked", "fail", mint_present, obs.get("authority_source"), obs.get("authority_fetched_at"), "Mint authority is set.")
    elif mint_present is False:
        c1 = check("C1", "Mint authority revoked", "pass", None, obs.get("authority_source"), obs.get("authority_fetched_at"), "Mint authority is null.")
    else:
        c1 = check("C1", "Mint authority revoked", "n/a", None, obs.get("authority_source"), obs.get("authority_fetched_at"), "RPC mint account was not read.")

    freeze_present = obs.get("freeze_authority_present", None)
    if freeze_present is True:
        c2 = check("C2", "Freeze authority revoked", "fail", freeze_present, obs.get("authority_source"), obs.get("authority_fetched_at"), "Freeze authority is set.")
    elif freeze_present is False:
        c2 = check("C2", "Freeze authority revoked", "pass", None, obs.get("authority_source"), obs.get("authority_fetched_at"), "Freeze authority is null.")
    else:
        c2 = check("C2", "Freeze authority revoked", "n/a", None, obs.get("authority_source"), obs.get("authority_fetched_at"), "RPC mint account was not read.")

    if obs.get("lp_on_bonding_curve"):
        c3 = check("C3", "LP burned or locked", "n/a", None, obs.get("lp_source"), obs.get("lp_fetched_at"), "Still on a bonding curve.")
    else:
        lp_pct = _num(obs.get("lp_locked_pct"))
        if lp_pct is None:
            c3 = check("C3", "LP burned or locked", "n/a", None, obs.get("lp_source"), obs.get("lp_fetched_at"), "No LP locked percent in the RugCheck report.")
        elif lp_pct < plan.LP_LOCK_FAIL_BELOW:
            c3 = check("C3", "LP burned or locked", "fail", lp_pct, obs.get("lp_source"), obs.get("lp_fetched_at"), "Locked or burned LP is under 80%.")
        else:
            c3 = check("C3", "LP burned or locked", "pass", lp_pct, obs.get("lp_source"), obs.get("lp_fetched_at"), "Locked or burned LP is at least 80%.")

    top10 = _num(obs.get("top10_pct_ex_pool"))
    if top10 is None:
        c4 = check("C4", "Top 10 holders ex pool and burn", "n/a", None, obs.get("holders_source"), obs.get("holders_fetched_at"), "Holder list with owners was not available.")
    elif top10 > plan.TOP10_WARN_ABOVE:
        c4 = check("C4", "Top 10 holders ex pool and burn", "warn", top10, obs.get("holders_source"), obs.get("holders_fetched_at"), "Top 10 non-pool wallets hold more than 25%.")
    else:
        c4 = check("C4", "Top 10 holders ex pool and burn", "pass", top10, obs.get("holders_source"), obs.get("holders_fetched_at"), "Top 10 non-pool wallets hold 25% or less.")

    largest = _num(obs.get("largest_non_pool_pct"))
    if largest is None:
        c5 = check("C5", "Largest non-pool wallet", "n/a", None, obs.get("holders_source"), obs.get("holders_fetched_at"), "Holder list with owners was not available.")
    elif largest > plan.LARGEST_WARN_ABOVE:
        c5 = check("C5", "Largest non-pool wallet", "warn", largest, obs.get("holders_source"), obs.get("holders_fetched_at"), "Largest non-pool wallet holds more than 15%.")
    else:
        c5 = check("C5", "Largest non-pool wallet", "pass", largest, obs.get("holders_source"), obs.get("holders_fetched_at"), "Largest non-pool wallet holds 15% or less.")

    liquidity = _num(obs.get("liquidity_usd"))
    if liquidity is None:
        c6 = check("C6", "Liquidity USD", "n/a", None, obs.get("liquidity_source"), obs.get("liquidity_fetched_at"), "DexScreener liquidity was missing.")
    elif liquidity < plan.LIQUIDITY_FAIL:
        c6 = check("C6", "Liquidity USD", "fail", liquidity, obs.get("liquidity_source"), obs.get("liquidity_fetched_at"), "Liquidity is under $25,000.")
    elif liquidity < plan.LIQUIDITY_WARN:
        c6 = check("C6", "Liquidity USD", "warn", liquidity, obs.get("liquidity_source"), obs.get("liquidity_fetched_at"), "Liquidity is under $50,000.")
    else:
        c6 = check("C6", "Liquidity USD", "pass", liquidity, obs.get("liquidity_source"), obs.get("liquidity_fetched_at"), "Liquidity is at least $50,000.")

    creator = _num(obs.get("creator_pct"))
    if creator is None:
        c7 = check("C7", "Creator wallet holding", "n/a", None, obs.get("creator_source"), obs.get("creator_fetched_at"), "Creator balance was not in the RugCheck report.")
    elif creator > plan.CREATOR_WARN_ABOVE:
        c7 = check("C7", "Creator wallet holding", "warn", creator, obs.get("creator_source"), obs.get("creator_fetched_at"), "Creator holds more than 5%.")
    else:
        c7 = check("C7", "Creator wallet holding", "pass", creator, obs.get("creator_source"), obs.get("creator_fetched_at"), "Creator holds 5% or less.")

    sold = _num(obs.get("dev_sold_pct_6h"))
    if sold is None:
        c8 = check("C8", "Creator sold in last 6h", "n/a", None, obs.get("dev_sold_source"), obs.get("dev_sold_fetched_at"), "RugCheck did not include a 6h creator-sale percent.")
    elif sold > plan.DEV_SOLD_WARN_ABOVE:
        c8 = check("C8", "Creator sold in last 6h", "warn", sold, obs.get("dev_sold_source"), obs.get("dev_sold_fetched_at"), "Creator sold more than half of the initial amount in 6h.")
    else:
        c8 = check("C8", "Creator sold in last 6h", "pass", sold, obs.get("dev_sold_source"), obs.get("dev_sold_fetched_at"), "Creator sale in 6h is 50% or less.")

    launches = obs.get("creator_launches_7d", None)
    if launches is None:
        c9 = check("C9", "Creator launches in 7 days", "n/a", None, obs.get("launches_source"), obs.get("launches_fetched_at"), "No dated creator-token list in the RugCheck report.")
    else:
        launches_n = int(launches)
        if launches_n >= plan.LAUNCHES_WARN_AT:
            c9 = check("C9", "Creator launches in 7 days", "warn", launches_n, obs.get("launches_source"), obs.get("launches_fetched_at"), "Creator launched 3 or more coins in 7 days.")
        else:
            c9 = check("C9", "Creator launches in 7 days", "pass", launches_n, obs.get("launches_source"), obs.get("launches_fetched_at"), "Creator launched fewer than 3 coins in 7 days.")

    linked = obs.get("bundled_linked", None)
    if linked is None:
        c10 = check(
            "C10",
            "Bundled launch",
            "n/a",
            None,
            obs.get("bundled_source"),
            obs.get("bundled_fetched_at"),
            "Best effort: no public field counts first-20 buyers funded by one wallet within 24h. Insider clusters are not used as a substitute.",
        )
    else:
        linked_n = int(linked)
        if linked_n >= plan.BUNDLE_FAIL_AT:
            c10 = check("C10", "Bundled launch", "fail", linked_n, obs.get("bundled_source"), obs.get("bundled_fetched_at"), "At least 5 early buyers share one funding wallet.")
        else:
            c10 = check("C10", "Bundled launch", "pass", linked_n, obs.get("bundled_source"), obs.get("bundled_fetched_at"), "Linked same-funder buyers are under 5.")

    buys = obs.get("m5_buys", None)
    sells = obs.get("m5_sells", None)
    honeypot_detail = "DexScreener publishes a 5-minute bucket, not 10 minutes. This check uses m5 buys and sells."
    if buys is None or sells is None:
        c11 = check("C11", "Honeypot txns", "n/a", None, obs.get("m5_source"), obs.get("m5_fetched_at"), honeypot_detail + " m5 counts were missing.")
    elif float(buys) > plan.HONEYPOT_BUYS_ABOVE and float(sells) == 0:
        c11 = check("C11", "Honeypot txns", "fail", {"m5_buys": buys, "m5_sells": sells}, obs.get("m5_source"), obs.get("m5_fetched_at"), honeypot_detail + " More than 10 buys and zero sells.")
    else:
        c11 = check("C11", "Honeypot txns", "pass", {"m5_buys": buys, "m5_sells": sells}, obs.get("m5_source"), obs.get("m5_fetched_at"), honeypot_detail)

    volume = _num(obs.get("volume_h1"))
    traders = obs.get("unique_traders_1h", None)
    ratio = None
    if volume is not None and liquidity is not None and liquidity > 0:
        ratio = volume / liquidity
    if ratio is None:
        c12 = check("C12", "Wash trading", "n/a", None, obs.get("wash_source"), obs.get("wash_fetched_at"), "1h volume or liquidity was missing, so the ratio was not computed.")
    elif ratio > plan.WASH_RATIO_ABOVE and traders is None:
        c12 = check("C12", "Wash trading", "n/a", {"volume_over_liquidity": ratio, "unique_traders_1h": None}, obs.get("wash_source"), obs.get("wash_fetched_at"), "Ratio is above 30, but unique traders were not in the public payload.")
    elif ratio > plan.WASH_RATIO_ABOVE and float(traders) < plan.WASH_TRADERS_BELOW:
        c12 = check("C12", "Wash trading", "warn", {"volume_over_liquidity": ratio, "unique_traders_1h": traders}, obs.get("wash_source"), obs.get("wash_fetched_at"), "1h volume / liquidity is above 30 and unique traders are under 100.")
    else:
        c12 = check("C12", "Wash trading", "pass", {"volume_over_liquidity": ratio, "unique_traders_1h": traders}, obs.get("wash_source"), obs.get("wash_fetched_at"), "Wash condition was not met.")

    created = parse_time(obs.get("pair_created_at"))
    fetched_age = parse_time(obs.get("age_fetched_at"))
    if created is None or fetched_age is None:
        c13 = check("C13", "Coin age", "n/a", None, obs.get("age_source"), obs.get("age_fetched_at"), "Pair creation time was missing.")
    else:
        age_s = (fetched_age - created).total_seconds()
        if age_s < -300:
            c13 = check("C13", "Coin age", "n/a", age_s, obs.get("age_source"), obs.get("age_fetched_at"), "Creation time is ahead of the fetch time.")
        elif age_s < plan.TOO_NEW_S:
            c13 = check("C13", "Coin age", "warn", age_s, obs.get("age_source"), obs.get("age_fetched_at"), "too new")
        else:
            c13 = check("C13", "Coin age", "pass", age_s, obs.get("age_source"), obs.get("age_fetched_at"), "Age is at least 3 minutes.")

    levels = obs.get("risk_levels", None)
    if levels is None:
        c14 = check("C14", "RugCheck risk list", "n/a", None, obs.get("risk_source"), obs.get("risk_fetched_at"), "RugCheck risk list was not read.")
    elif any(level == "danger" for level in levels):
        c14 = check("C14", "RugCheck risk list", "fail", levels, obs.get("risk_source"), obs.get("risk_fetched_at"), "RugCheck lists a danger item.")
    elif any(level == "warn" for level in levels):
        c14 = check("C14", "RugCheck risk list", "warn", levels, obs.get("risk_source"), obs.get("risk_fetched_at"), "RugCheck lists a warn item and no danger item.")
    else:
        c14 = check("C14", "RugCheck risk list", "pass", levels, obs.get("risk_source"), obs.get("risk_fetched_at"), "No danger or warn items.")

    quotes = bot_flag(texts)
    if quotes:
        d1 = check(
            "D1",
            "Description talks to bots",
            "warn",
            quotes,
            obs.get("texts_source"),
            obs.get("texts_fetched_at"),
            "description talks to bots",
        )
    else:
        d1 = check("D1", "Description talks to bots", "pass", None, obs.get("texts_source"), obs.get("texts_fetched_at"), "No instruction-like token text.")

    checks = [c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, d1]
    verdict = verdict_of(checks)
    return {
        "label": plan.LABEL,
        "mint": obs.get("mint"),
        "symbol": obs.get("symbol"),
        "name": obs.get("name"),
        "verdict": verdict,
        "score": tally_score(checks),
        "checks": checks,
        "price_usd": _num(obs.get("price_usd")),
        "price_source": obs.get("price_source"),
        "price_fetched_at": obs.get("price_fetched_at"),
        "audited_at": iso(now),
    }


def observation_from_sources(candidate, pair, rug, rpc, fetched, now):
    """Copy real fields into an observation. Absent fields stay absent."""
    info = (pair or {}).get("info") if isinstance(pair, dict) else None
    websites = []
    socials = []
    if isinstance(info, dict):
        for site in info.get("websites") or []:
            if isinstance(site, dict) and site.get("url"):
                websites.append(str(site["url"]))
        for social in info.get("socials") or []:
            if isinstance(social, dict):
                socials.append(" ".join(str(social.get(key) or "") for key in ("platform", "handle", "url")))
    profile_text = (candidate or {}).get("description") or ""
    base = (pair or {}).get("baseToken") if isinstance(pair, dict) else None
    symbol = (candidate or {}).get("symbol") or (base or {}).get("symbol") or ""
    name = (candidate or {}).get("name") or (base or {}).get("name") or ""
    txns = (pair or {}).get("txns") if isinstance(pair, dict) else None
    m5 = txns.get("m5") if isinstance(txns, dict) else None
    volume = (pair or {}).get("volume") if isinstance(pair, dict) else None
    liquidity = (pair or {}).get("liquidity") if isinstance(pair, dict) else None
    top10, largest = holder_stats(rug) if isinstance(rug, dict) else (None, None)
    lp_pct, bonding = lp_from_report(rug) if isinstance(rug, dict) else (None, False)
    rpc_ok = isinstance(rpc, dict) and rpc.get("ok")
    return {
        "now": iso(now),
        "mint": (candidate or {}).get("mint"),
        "symbol": symbol,
        "name": name,
        "texts": {
            "name": name,
            "symbol": symbol,
            "description": profile_text,
            "websites": " ".join(websites),
            "socials": " ".join(socials),
        },
        "texts_source": fetched.get("dex_source"),
        "texts_fetched_at": fetched.get("dex"),
        "mint_authority_present": (rpc.get("mint_authority") is not None) if rpc_ok else None,
        "freeze_authority_present": (rpc.get("freeze_authority") is not None) if rpc_ok else None,
        "authority_source": fetched.get("rpc_source"),
        "authority_fetched_at": fetched.get("rpc"),
        "lp_locked_pct": lp_pct,
        "lp_on_bonding_curve": bonding,
        "lp_source": fetched.get("rug_source"),
        "lp_fetched_at": fetched.get("rug"),
        "top10_pct_ex_pool": top10,
        "largest_non_pool_pct": largest,
        "holders_source": fetched.get("rug_source"),
        "holders_fetched_at": fetched.get("rug"),
        "liquidity_usd": _num((liquidity or {}).get("usd")) if isinstance(liquidity, dict) else None,
        "liquidity_source": fetched.get("dex_source"),
        "liquidity_fetched_at": fetched.get("dex"),
        "creator_pct": creator_pct(rug) if isinstance(rug, dict) else None,
        "creator_source": fetched.get("rug_source"),
        "creator_fetched_at": fetched.get("rug"),
        "dev_sold_pct_6h": dev_sold_pct(rug, now) if isinstance(rug, dict) else None,
        "dev_sold_source": fetched.get("rug_source"),
        "dev_sold_fetched_at": fetched.get("rug"),
        "creator_launches_7d": launches_7d(rug, now) if isinstance(rug, dict) else None,
        "launches_source": fetched.get("rug_source"),
        "launches_fetched_at": fetched.get("rug"),
        "bundled_linked": bundled_links(rug) if isinstance(rug, dict) else None,
        "bundled_source": fetched.get("rug_source"),
        "bundled_fetched_at": fetched.get("rug"),
        "m5_buys": None if not isinstance(m5, dict) else m5.get("buys"),
        "m5_sells": None if not isinstance(m5, dict) else m5.get("sells"),
        "m5_source": fetched.get("dex_source"),
        "m5_fetched_at": fetched.get("dex"),
        "volume_h1": _num((volume or {}).get("h1")) if isinstance(volume, dict) else None,
        "unique_traders_1h": None,
        "wash_source": fetched.get("dex_source"),
        "wash_fetched_at": fetched.get("dex"),
        "pair_created_at": (pair or {}).get("pairCreatedAt") if isinstance(pair, dict) else None,
        "age_source": fetched.get("dex_source"),
        "age_fetched_at": fetched.get("dex"),
        "risk_levels": risk_levels(rug) if isinstance(rug, dict) else None,
        "risk_source": fetched.get("rug_source"),
        "risk_fetched_at": fetched.get("rug"),
        "price_usd": _num((pair or {}).get("priceUsd")) if isinstance(pair, dict) else None,
        "price_source": fetched.get("dex_source"),
        "price_fetched_at": fetched.get("dex"),
    }


def rpc_call(method, params):
    if method not in ALLOWED_RPC:
        raise RuntimeError("blocked rpc method")
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last = None
    for url in RPCS:
        try:
            payload = public_http.fetch_json(url, method="POST", body=body, timeout=25)
        except public_http.SourceUnavailable as err:
            last = err
            continue
        if isinstance(payload, dict) and payload.get("error"):
            last = payload["error"]
            continue
        return payload, url
    raise public_http.SourceUnavailable("rpc down: %s" % last)


def read_mint_account(mint):
    payload, url = rpc_call("getAccountInfo", [mint, {"encoding": "base64"}])
    value = ((payload or {}).get("result") or {}).get("value")
    if not isinstance(value, dict):
        return {"ok": False, "mint_authority": None, "freeze_authority": None}, url
    data = value.get("data")
    if not isinstance(data, list) or not data:
        return {"ok": False, "mint_authority": None, "freeze_authority": None}, url
    raw = base64.b64decode(data[0])
    parsed = parse_mint_account(raw)
    return parsed, url


def read_largest_accounts(mint):
    """Fetched for the record. Owners are not in this method, so it does not set C4 or C5."""
    payload, url = rpc_call("getTokenLargestAccounts", [mint])
    value = ((payload or {}).get("result") or {}).get("value")
    count = len(value) if isinstance(value, list) else None
    return count, url


def fetch_pairs(mints):
    if not mints:
        return {}
    url = DEX_TOKEN_URL + ",".join(mints)
    payload = public_http.fetch_json(url, timeout=30)
    rows = payload if isinstance(payload, list) else (payload or {}).get("pairs") or []
    best = {}
    for pair in rows:
        if not isinstance(pair, dict):
            continue
        base = (pair.get("baseToken") or {}).get("address")
        if base not in mints:
            continue
        liquidity = _num(((pair.get("liquidity") or {}).get("usd")))
        current = best.get(base)
        current_liq = _num(((current or {}).get("liquidity") or {}).get("usd")) or -1
        if current is None or (liquidity or -1) > current_liq:
            best[base] = pair
    return best


def latest_candidates():
    marker = store.read_json("latest_run.json")
    if not marker:
        return [], None
    run_id = marker.get("run_id")
    rows = [row for row in store.read_jsonl("candidates.jsonl") if row.get("run_id") == run_id]
    return rows, run_id


def open_cards():
    graded = {(row.get("mint"), row.get("t0")) for row in store.read_jsonl("graded.jsonl")}
    cards = []
    for row in store.read_jsonl("cards.jsonl"):
        if (row.get("mint"), row.get("t0")) in graded:
            continue
        cards.append(row)
    return cards


def already_audited(run_id):
    return {row.get("mint") for row in store.read_jsonl("audits.jsonl") if row.get("run_id") == run_id}


def card_exists(mint, now):
    for row in open_cards():
        if row.get("mint") != mint:
            continue
        opened = parse_time(row.get("t0"))
        if opened and (now - opened).total_seconds() < plan.HORIZON_S:
            return True
    return False


def audit_candidate(candidate, pair, now):
    fetched = {
        "dex": iso(now),
        "dex_source": DEX_TOKEN_URL + (candidate.get("mint") or ""),
        "rug": None,
        "rug_source": RUG_URL.format(mint=candidate.get("mint") or ""),
        "rpc": None,
        "rpc_source": RPCS[0],
    }
    errors = []
    rug = None
    try:
        rug = public_http.fetch_json(fetched["rug_source"], timeout=40)
        fetched["rug"] = iso(utc_now())
    except public_http.SourceUnavailable as err:
        errors.append("rugcheck: %s" % err)
        fetched["rug"] = iso(utc_now())
    rpc = None
    try:
        rpc, rpc_url = read_mint_account(candidate["mint"])
        fetched["rpc"] = iso(utc_now())
        fetched["rpc_source"] = rpc_url + " getAccountInfo"
    except public_http.SourceUnavailable as err:
        errors.append("rpc getAccountInfo: %s" % err)
        fetched["rpc"] = iso(utc_now())
    try:
        time.sleep(0.15)
        count, largest_url = read_largest_accounts(candidate["mint"])
        fetched["rpc_largest"] = count
        fetched["rpc_largest_source"] = largest_url + " getTokenLargestAccounts"
    except public_http.SourceUnavailable as err:
        errors.append("rpc getTokenLargestAccounts: %s" % err)
    obs = observation_from_sources(candidate, pair, rug if isinstance(rug, dict) else None, rpc, fetched, now)
    result = audit_observation(obs)
    result["run_id"] = candidate.get("run_id")
    result["pair_address"] = (pair or {}).get("pairAddress") or candidate.get("pair_address")
    result["pair_url"] = (pair or {}).get("url") or candidate.get("url")
    result["liquidity_usd"] = obs.get("liquidity_usd")
    result["age_seconds"] = next((item["value"] for item in result["checks"] if item["id"] == "C13"), None)
    result["errors"] = errors
    result["rpc_largest_accounts"] = fetched.get("rpc_largest")
    return result


def write_card(result, now):
    if result.get("price_usd") is None:
        return None
    if card_exists(result.get("mint"), now):
        return None
    card = {
        "label": plan.LABEL,
        "mint": result.get("mint"),
        "symbol": result.get("symbol"),
        "name": result.get("name"),
        "t0": result.get("audited_at"),
        "price_t0": result.get("price_usd"),
        "price_source": result.get("price_source"),
        "price_fetched_at": result.get("price_fetched_at"),
        "verdict": result.get("verdict"),
        "score": result.get("score"),
        "plan": plan.plan_dict(),
    }
    store.append_jsonl("cards.jsonl", card)
    return card


def snapshot(mint, price, source, moment):
    if price is None:
        return
    store.append_jsonl("snapshots.jsonl", {
        "mint": mint,
        "t": iso(moment),
        "price_usd": price,
        "source": source,
        "fetched_at": iso(moment),
    })


def main():
    import board

    candidates, run_id = latest_candidates()
    if not candidates:
        print("memescan audit: no candidates for the latest scan. Skipping.")
        board.write_board()
        return 0
    done = already_audited(run_id)
    pending = [row for row in candidates if row.get("mint") not in done]
    if not pending:
        print("memescan audit: run %s already audited." % run_id)
        board.write_board()
        return 0
    try:
        pairs = fetch_pairs([row["mint"] for row in pending if row.get("mint")])
    except public_http.SourceUnavailable as err:
        print("memescan audit: DexScreener down (%s). Skipping run." % err)
        return 0
    now = utc_now()
    for candidate in pending:
        mint = candidate.get("mint")
        pair = pairs.get(mint)
        if pair is None:
            print("memescan audit: no pair for %s. Checks that need DexScreener will be n/a." % mint)
        try:
            result = audit_candidate(candidate, pair, utc_now())
        except public_http.SourceUnavailable as err:
            print("memescan audit: skipped %s (%s)" % (mint, err))
            continue
        store.append_jsonl("audits.jsonl", result)
        write_card(result, now)
        snapshot(mint, result.get("price_usd"), result.get("price_source"), parse_time(result.get("price_fetched_at")) or now)
        print("%s %s %s score %s" % (result.get("symbol"), mint, result.get("verdict"), result.get("score")))
        time.sleep(0.25)
    board.write_board()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
