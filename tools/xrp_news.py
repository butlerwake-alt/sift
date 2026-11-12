#!/usr/bin/env python3
"""Gather recent XRP / Ripple news from free, keyless sources and write data/xrp_news.json.

Lives at tools/xrp_news.py on the SIFT site. From the site root:

    /workspace/qvenv/bin/python tools/xrp_news.py

That writes data/xrp_news.json in the site (not tools/data/). If a run fails,
the previous JSON file is left in place.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import hashlib
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree as ET
from typing import Any

import requests
from bs4 import BeautifulSoup

try:
    from zoneinfo import ZoneInfo
    ET_ZONE = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET_ZONE = timezone(timedelta(hours=-5))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "tools" else HERE
OUT_DIR = os.path.join(ROOT, "data")
OUT_FILE = os.path.join(OUT_DIR, "xrp_news.json")
TMP_FILE = OUT_FILE + ".tmp"

LOOKBACK_DAYS = 16  # ~14 days, with a little slack for time zones
MAX_ITEMS = 15
REQUEST_TIMEOUT = 25
SLEEP_BETWEEN = 0.35

UA = (
    "SIFTResearchBot/1.0 (educational paper-trading research; "
    "+https://butlerwake-alt.github.io/sift/)"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
# SEC requires a descriptive user-agent with a contact. This host often still
# returns 403 to datacenter IPs; official EDGAR URLs are kept for readers.
SEC_HEADERS = {
    "User-Agent": "SIFT Research butlerwake-alt.github.io/sift educational-bot",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/atom+xml, application/json, text/html",
}

# ---------------------------------------------------------------------------
# Source lists
# ---------------------------------------------------------------------------

PRIMARY_DOMAINS = {
    "ripple.com",
    "treasury.ripple.com",
    "xrpl.org",
    "pages.xrpl.foundation",
    "xrpl.foundation",
    "sec.gov",
    "www.sec.gov",
    "occ.gov",
    "www.occ.gov",
    "occ.treas.gov",
    "www.occ.treas.gov",
    "cftc.gov",
    "www.cftc.gov",
    "justice.gov",
    "www.justice.gov",
    "federalregister.gov",
    "www.federalregister.gov",
    "courtlistener.com",
    "www.courtlistener.com",
    "cmegroup.com",
    "www.cmegroup.com",
    "nasdaq.com",
    "www.nasdaq.com",
    "avivainvestors.com",
    "www.avivainvestors.com",
    "investors.aviva.co.uk",
    "robinhood.com",
    "newsroom.robinhood.com",
    "coinbase.com",
    "www.coinbase.com",
}

# Outlets we will cite. Lower-quality / clickbait domains are not on this list.
REPUTABLE_DOMAINS = PRIMARY_DOMAINS | {
    "coindesk.com",
    "www.coindesk.com",
    "cointelegraph.com",
    "theblock.co",
    "www.theblock.co",
    "decrypt.co",
    "blockworks.co",
    "thedefiant.io",
    "www.thedefiant.io",
    "reuters.com",
    "www.reuters.com",
    "bloomberg.com",
    "www.bloomberg.com",
    "wsj.com",
    "www.wsj.com",
    "ft.com",
    "www.ft.com",
    "apnews.com",
    "www.apnews.com",
    "bbc.com",
    "www.bbc.com",
    "bbc.co.uk",
    "www.bbc.co.uk",
    "cnbc.com",
    "www.cnbc.com",
    "forbes.com",
    "www.forbes.com",
    "fortune.com",
    "fortune.com",
    "nytimes.com",
    "www.nytimes.com",
    "washingtonpost.com",
    "www.washingtonpost.com",
    "axios.com",
    "www.axios.com",
    "barrons.com",
    "www.barrons.com",
    "marketwatch.com",
    "www.marketwatch.com",
    "americanbanker.com",
    "www.americanbanker.com",
    "bankingdive.com",
    "www.bankingdive.com",
    "dlnews.com",
    "www.dlnews.com",
    "crypto.news",
    "law360.com",
    "www.law360.com",
    "bloomberg.com",
    "nikkei.com",
    "asia.nikkei.com",
}

SOURCE_DISPLAY = {
    "ripple.com": "Ripple",
    "treasury.ripple.com": "Ripple Treasury",
    "xrpl.org": "XRP Ledger",
    "pages.xrpl.foundation": "XRP Ledger Foundation",
    "xrpl.foundation": "XRP Ledger Foundation",
    "sec.gov": "SEC EDGAR",
    "www.sec.gov": "SEC EDGAR",
    "occ.gov": "OCC",
    "www.occ.gov": "OCC",
    "coindesk.com": "CoinDesk",
    "www.coindesk.com": "CoinDesk",
    "cointelegraph.com": "Cointelegraph",
    "theblock.co": "The Block",
    "www.theblock.co": "The Block",
    "decrypt.co": "Decrypt",
    "blockworks.co": "Blockworks",
    "thedefiant.io": "The Defiant",
    "www.thedefiant.io": "The Defiant",
    "reuters.com": "Reuters",
    "www.reuters.com": "Reuters",
    "bloomberg.com": "Bloomberg",
    "www.bloomberg.com": "Bloomberg",
    "americanbanker.com": "American Banker",
    "www.americanbanker.com": "American Banker",
    "bankingdive.com": "Banking Dive",
    "www.bankingdive.com": "Banking Dive",
    "dlnews.com": "DL News",
    "www.dlnews.com": "DL News",
    "crypto.news": "crypto.news",
    "cmegroup.com": "CME Group",
    "www.cmegroup.com": "CME Group",
    "avivainvestors.com": "Aviva Investors",
    "www.avivainvestors.com": "Aviva Investors",
}

# Drop these even if they appear in Google News.
EXCLUDE_DOMAINS = {
    "twitter.com",
    "x.com",
    "t.me",
    "reddit.com",
    "www.reddit.com",
    "youtube.com",
    "www.youtube.com",
    "tiktok.com",
    "facebook.com",
    "www.facebook.com",
    "truthsocial.com",
    "medium.com",  # often paid/promoted posts; allow only if already corroborated
}

SPAM_PATTERNS = re.compile(
    r"(price prediction|what could xrp be worth|how much xrp do you need|"
    r"what will \S+ xrp be worth|where will xrp be in|"
    r"will xrp (go|reach|hit|hold)|can xrp reach|"
    r"is xrp (dead|the best)|is it better to buy|"
    r"analyst (bets|eyes|predicts)|eyes \$\d|"
    r"meta ai predicts|chatgpt|to the moon|"
    r"next peak|secret plan to \$\d|"
    r"should (you|investors) (buy|worry)|best cryptocurrency you can buy|"
    r"failed breakout|oversold signals have preceded)",
    re.I,
)

SPONSORED_PATTERNS = re.compile(
    r"(sponsored|press release from|paid content|partner content|"
    r"advertisement|contrib(uted|utor) content)",
    re.I,
)

# Daily price recaps, not news events.
MARKET_NOISE = re.compile(
    r"(drops? \d+%|fell \d+%|slides? as liquidations|lagging bitcoin|"
    r"selloff wipes out|whipsaw|price faces new risk|lowest since|"
    r"crypto today:|steady, but )",
    re.I,
)

RUMOR_PATTERNS = re.compile(
    r"\b(rumor|rumour|unconfirmed|reportedly|alleged(ly)?|speculation|"
    r"sources say|according to people familiar|unverified)\b",
    re.I,
)

RELEVANT = re.compile(
    r"\b(xrp|xrpl|rlusd|evernorth|xrpn|ripple labs|ripple usd|"
    r"xrp ledger|ripplenet)\b",
    re.I,
)
# "Ripple" alone is noisy (physics, NYT reviews). Require a finance cue.
RIPPLE_FINANCE = re.compile(
    r"\bripple\b.{0,80}\b(bank|charter|occ|sec|etf|stablecoin|ledger|"
    r"crypto|token|rlusd|xrp|custody|trust|garlinghouse|robinhood|"
    r"coinbase|bny|aviva|swell)\b|"
    r"\b(bank|charter|occ|sec|etf|stablecoin|ledger|crypto|token|rlusd|"
    r"xrp|custody|trust|garlinghouse|robinhood|coinbase|bny|aviva|swell)"
    r"\b.{0,80}\bripple\b",
    re.I,
)

# Hand-written neutral summaries for known stories (keyed by a distinctive
# URL path fragment). These are original paraphrases, not copied ledes.
SUMMARY_OVERRIDES = {
    "ripple-receives-final-occ-approval-to-establish-national-trust-bank":
        "The Office of the Comptroller of the Currency gave final approval for Ripple National Trust Bank, a federally supervised trust bank that may manage RLUSD reserves and offer fiduciary digital-asset custody; RLUSD would still be issued by Ripple’s New York trust company.",
    "occ-gives-final-approval-to-ripples-national-trust-charter":
        "The Office of the Comptroller of the Currency gave final approval for Ripple National Trust Bank, a federally supervised trust bank that may manage RLUSD reserves and offer fiduciary digital-asset custody; RLUSD would still be issued by Ripple’s New York trust company.",
    "ripple-gets-a-final-go-ahead-to-launch-its-own-u-s-national-trust-bank":
        "The Office of the Comptroller of the Currency gave final approval for Ripple National Trust Bank, a federally supervised trust bank that may manage RLUSD reserves and offer fiduciary digital-asset custody; RLUSD would still be issued by Ripple’s New York trust company.",
    "ripple-wins-final-us-approval-for-national-trust-bank":
        "The Office of the Comptroller of the Currency gave final approval for Ripple National Trust Bank, a federally supervised trust bank that may manage RLUSD reserves and offer fiduciary digital-asset custody; RLUSD would still be issued by Ripple’s New York trust company.",
    "ripple-and-robinhood-partner-to-power-the-next-generation-of-finance":
        "Ripple and Robinhood said they will expand use of the RLUSD stablecoin across Robinhood’s retail and institutional businesses, and that Robinhood plans to use Ripple Treasury and Ripple Prime.",
    "ripple-robinhood-expand-partnership-rlusd":
        "Ripple and Robinhood said they will expand use of the RLUSD stablecoin across Robinhood’s retail and institutional businesses, and that Robinhood plans to use Ripple Treasury and Ripple Prime.",
    "ripple-and-coinbase-partner-to-expand-access-to-rlusd":
        "Ripple and Coinbase announced that RLUSD can be traded and managed on Coinbase’s prime, exchange and retail platforms, with transfers supported on the XRP Ledger, Base and Ethereum.",
    "ripple-expands-collaboration-with-bny":
        "Ripple and BNY said they are broadening digital-asset custody work and exploring tokenized trade-finance uses, including support for assets issued on the XRP Ledger.",
    "c2fo-and-ripple-partner-to-modernize-trade-finance":
        "C2FO and Ripple said financing and settlement activity for C2FO’s Instant Pay product will be brought onto the XRP Ledger.",
    "aviva-investors-expands-its-tokenised-offering":
        "Aviva Investors launched a tokenized share class of its roughly £22 billion sterling liquidity fund on the XRP Ledger and invested £50 million of its own money in the new class.",
    "aviva-investors-launches-tokenized-share-class":
        "Aviva Investors launched a tokenized share class of its roughly £22 billion sterling liquidity fund on the XRP Ledger and invested £50 million of its own money in the new class.",
    "aviva-tokenized-liquidity-fund-explained":
        "Aviva Investors launched a tokenized share class of its roughly £22 billion sterling liquidity fund on the XRP Ledger and invested £50 million of its own money in the new class.",
    "ripple-treasury-introduces-always-on-corporate-treasury-platform":
        "Ripple announced an always-on corporate treasury platform that combines cash management, payments, liquidity, stablecoins and custody for business customers.",
    "always-on-corporate-treasury-platform":
        "Ripple announced an always-on corporate treasury platform that combines cash management, payments, liquidity, stablecoins and custody for business customers.",
    "ripple-and-waterorg-deepen-partnership":
        "Ripple and Water.org said their partnership has reached one million people and will expand to use Ripple Payments, RLUSD and digital-asset custody.",
    "ripple-reports-banner-year-approaching-900m":
        "At its Swell conference, Ripple said it is on track to finish 2026 with about $900 million in annualized product revenue and pointed to new institutional partnerships; the figure is the company’s own claim.",
    "0001628280-26-072223":
        "A final SEC prospectus dated Nov. 9 lets existing holders of Evernorth (Nasdaq: XRPN), the XRP treasury company, resell up to 73.7 million Class A shares; Evernorth receives no proceeds from those sales.",
    "9999999995-26-003488":
        "A final SEC prospectus dated Nov. 9 lets existing holders of Evernorth (Nasdaq: XRPN), the XRP treasury company, resell up to 73.7 million Class A shares; Evernorth receives no proceeds from those sales.",
    "evernorth-slides-24-after-73-7-million-share-filing":
        "After a final SEC prospectus covering the potential resale of up to 73.7 million Evernorth (XRPN) shares became effective, the stock fell sharply in the next session; the filing does not require those holders to sell.",
    "xrp-ledger-maps-out-quantum-proof-accounts":
        "The XRP Ledger Foundation published a design that would let account owners add a quantum-resistant ML-DSA-44 signing key and retire the old one, with no change to the base fee and a targeted transition around 2028; it is still a proposal, not an activated upgrade.",
    "protocol-roadmap/research/quantum":
        "The XRP Ledger Foundation published a design that would let account owners add a quantum-resistant ML-DSA-44 signing key and retire the old one, with no change to the base fee and a targeted transition around 2028; it is still a proposal, not an activated upgrade.",
    "xrp-ledger-quantum-resistant-accounts-2028":
        "The XRP Ledger Foundation published a design that would let account owners add a quantum-resistant ML-DSA-44 signing key and retire the old one, with no change to the base fee and a targeted transition around 2028; it is still a proposal, not an activated upgrade.",
    "xrp-ledger-closes-bug-that-let-approved-token-burners-create-new-tokens":
        "CoinDesk reported that an XRP Ledger amendment took effect to close a loophole that could have let accounts authorized only to burn issued tokens also create new ones; the report said XRP’s own supply was not affected.",
    "xrp-ledger-set-to-fix-flaw-that-could-let-stablecoin-partners-print-new-tokens":
        "CoinDesk reported that an XRP Ledger amendment was set to close a loophole that could have let accounts authorized only to burn issued tokens also create new ones; the report said XRP’s own supply would not be affected.",
    "xrp-ledger-developers-tighten-the-rules-for-who-can-hold-restricted-tokens":
        "CoinDesk reported that XRP Ledger developers proposed rule changes so restricted tokens cannot remain with accounts the issuer has not approved, except to be returned to the issuer.",
}

# Stories that are clearly the same event, used to merge across outlets.
STORY_KEYS = [
    ("occ_trust_bank", re.compile(r"(national trust (bank|charter)|occ.{0,40}(approval|charter)|final (occ|us) approval)", re.I)),
    ("revenue_900m", re.compile(r"900\s*m|\$900|banner year|annual(?:ized)? product revenue", re.I)),
    ("robinhood", re.compile(r"robinhood", re.I)),
    ("coinbase_rlusd", re.compile(r"coinbase.{0,40}rlusd|rlusd.{0,40}coinbase", re.I)),
    ("bny", re.compile(r"\bbny\b|bank of new york", re.I)),
    ("c2fo", re.compile(r"c2fo", re.I)),
    ("aviva", re.compile(r"aviva", re.I)),
    ("treasury_platform", re.compile(r"always-on corporate treasury|treasury platform to modernize", re.I)),
    ("waterorg", re.compile(r"water\.org|waterorg", re.I)),
    ("evernorth_resale", re.compile(r"evernorth|xrpn|73\.7", re.I)),
    ("quantum_keys", re.compile(r"quantum[- ]?(proof|resistant)|post-quantum|ml-dsa", re.I)),
    ("token_print_bug", re.compile(r"(print(?:ed)? new tokens|creation of new tokens|create new tokens|token[- ]burners|disclosed bug.{0,40}tokens)", re.I)),
    ("restricted_tokens", re.compile(r"restricted['’]? tokens", re.I)),
]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


def get(url: str, headers: dict | None = None, retries: int = 2) -> requests.Response | None:
    hdrs = headers or HEADERS
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=hdrs, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            last = r
            # Retry transient blocks.
            if r.status_code in (429, 502, 503, 504) and attempt < retries:
                time.sleep(1.2 * (attempt + 1))
                continue
            return r
        except requests.RequestException as exc:
            last = exc  # type: ignore[assignment]
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))
                continue
            log(f"  request failed {url[:90]}: {exc}")
            return None
    return last if isinstance(last, requests.Response) else None


def host_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def registrable(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def display_name(url: str, fallback: str = "") -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if host in SOURCE_DISPLAY:
        return SOURCE_DISPLAY[host]
    bare = host.removeprefix("www.")
    if bare in SOURCE_DISPLAY:
        return SOURCE_DISPLAY[bare]
    if fallback:
        return fallback
    if bare:
        return bare.split(".")[0].replace("-", " ").title()
    return "Source"


def is_primary(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host in PRIMARY_DOMAINS or host.removeprefix("www.") in {
        h.removeprefix("www.") for h in PRIMARY_DOMAINS
    }


def is_reputable(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host in REPUTABLE_DOMAINS or host.removeprefix("www.") in {
        h.removeprefix("www.") for h in REPUTABLE_DOMAINS
    }


def clean_url(url: str) -> str:
    if not url:
        return url
    url = url.strip()
    # Drop tracking query params, keep EDGAR query strings that matter.
    parts = urllib.parse.urlsplit(url)
    if "news.google.com" in parts.netloc:
        return url  # resolved later or dropped
    q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    drop = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "oc"}
    q = [(k, v) for k, v in q if k.lower() not in drop]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(q), parts.fragment))


def cutoff() -> datetime:
    # Compare against the start of the day, LOOKBACK_DAYS ago, so a story
    # published on that calendar date is not dropped by the time of day.
    now = datetime.now(tz=ET_ZONE)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=LOOKBACK_DAYS)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for parser in (_parse_rfc2822, _parse_iso, _parse_human):
        dt = parser(value)
        if dt:
            return dt
    return None


def _as_et(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ET_ZONE)


def _parse_rfc2822(value: str) -> datetime | None:
    try:
        return _as_et(parsedate_to_datetime(value))
    except Exception:
        return None


def _parse_iso(value: str) -> datetime | None:
    try:
        raw = value.replace("Z", "+00:00")
        return _as_et(datetime.fromisoformat(raw))
    except Exception:
        return None


def _parse_human(value: str) -> datetime | None:
    value = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", value)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%Y-%m-%d", "%b %d %Y"):
        try:
            return datetime.strptime(value[:40].strip(), fmt).replace(tzinfo=ET_ZONE)
        except Exception:
            continue
    return None


def strip_html(text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str) -> str:
    title = strip_html(title)
    title = re.sub(r"^(Ripple news:|XRP news today:|Breaking:|Update:)\s*", "", title, flags=re.I)
    # Drop trailing " - Source" / " | Source"
    title = re.sub(r"\s+[\-–—|]\s+(Ripple|CoinDesk|Cointelegraph|Yahoo Finance|Yahoo Tech|"
                   r"The Block|Decrypt|Blockworks|The Defiant|Reuters|Bloomberg|"
                   r"American Banker|Banking Dive|DL News|crypto\.news|SEC\.gov|"
                   r"CME Group|24/7 Wall St\.|NerdWallet|TradingView)\s*$",
                   "", title, flags=re.I)
    title = title.replace("’", "'").replace("“", '"').replace("”", '"')
    title = re.sub(r"\s+", " ", title).strip(" -|")
    return title


def title_fingerprint(title: str) -> str:
    t = normalize_title(title).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    stop = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with",
            "its", "as", "at", "by", "from", "is", "are", "be", "new"}
    tokens = [w for w in t.split() if w not in stop and len(w) > 1]
    return " ".join(tokens[:12])


def story_key(title: str, url: str = "") -> str | None:
    blob = f"{title} {url}"
    for key, pat in STORY_KEYS:
        if pat.search(blob):
            return key
    return None


def is_relevant(title: str, summary: str = "") -> bool:
    blob = f"{title} {summary}"
    if RELEVANT.search(blob):
        return True
    if re.search(r"\bripple\b", blob, re.I) and RIPPLE_FINANCE.search(blob):
        return True
    return False


def is_spam(title: str, summary: str = "") -> bool:
    blob = f"{title} {summary}"
    if SPAM_PATTERNS.search(blob):
        return True
    if SPONSORED_PATTERNS.search(blob):
        return True
    return False


# ---------------------------------------------------------------------------
# RSS / HTML fetchers
# ---------------------------------------------------------------------------

def parse_rss(xml_bytes: bytes) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    ns = {"atom": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/elements/1.1/"}

    def text(el: ET.Element, tag: str) -> str:
        child = el.find(tag)
        if child is not None and (child.text or "").strip():
            return (child.text or "").strip()
        for c in el:
            if c.tag.endswith(tag) and (c.text or "").strip():
                return (c.text or "").strip()
        return ""

    for it in root.findall(".//item"):
        title = text(it, "title")
        link = text(it, "link") or text(it, "guid")
        pub = text(it, "pubDate") or text(it, "date") or text(it, "dc:date")
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        desc = strip_html(text(it, "description") or text(it, "summary"))
        items.append({"title": title, "url": link, "pub": pub, "source": source, "desc": desc})

    if items:
        return items

    for it in root.findall(".//atom:entry", ns) or root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        title = (it.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link = ""
        for ln in it.findall("{http://www.w3.org/2005/Atom}link"):
            href = ln.get("href") or ""
            if href and (ln.get("rel") in (None, "alternate") or not link):
                link = href
        pub = (it.findtext("{http://www.w3.org/2005/Atom}updated")
               or it.findtext("{http://www.w3.org/2005/Atom}published") or "")
        desc = strip_html(it.findtext("{http://www.w3.org/2005/Atom}summary")
                          or it.findtext("{http://www.w3.org/2005/Atom}content") or "")
        items.append({"title": title, "url": link, "pub": pub, "source": "", "desc": desc})
    return items


def fetch_rss(url: str, label: str) -> list[dict]:
    r = get(url)
    if r is None or r.status_code != 200:
        status = r.status_code if r is not None else "err"
        log(f"  RSS {label}: {status}")
        return []
    items = parse_rss(r.content)
    log(f"  RSS {label}: {len(items)} items")
    return items


def google_news(query: str) -> list[dict]:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    return fetch_rss(url, f"gnews:{query[:40]}")


def try_jina(url: str) -> str:
    for prefix in ("https://r.jina.ai/http://", "https://r.jina.ai/https://"):
        target = prefix + re.sub(r"^https?://", "", url)
        r = get(target)
        if r is not None and r.status_code == 200 and "Vercel Security" not in r.text:
            text = r.text
            if len(text) > 400 and "markdown content" in text.lower() or len(text) > 800:
                return text
    return ""


def fetch_ripple_press() -> list[dict]:
    """Official Ripple press-release index, with a Jina fallback if Cloudflare blocks us."""
    items: list[dict] = []
    urls = [
        "https://ripple.com/press-releases/",
        "https://r.jina.ai/https://ripple.com/press-releases/",
        "https://r.jina.ai/http://ripple.com/press-releases/",
    ]
    body = ""
    for url in urls:
        r = get(url)
        if r is None:
            continue
        if r.status_code == 200 and "Vercel Security" not in r.text and len(r.text) > 800:
            body = r.text
            log(f"  Ripple press via {url[:60]} ({len(body)} bytes)")
            break
        log(f"  Ripple press {url[:60]} -> {r.status_code}")
    if not body:
        return items

    # Markdown from Jina: [title](url) followed by a date line.
    md_pat = re.compile(
        r"\[([^\]]{10,220})\]\((https://ripple.com/ripple-press/[^)\s]+)\)\s+"
        r"([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})",
        re.S,
    )
    for title, url, date in md_pat.findall(body):
        items.append({"title": strip_html(title), "url": url, "pub": date, "source": "Ripple", "desc": ""})

    if not items:
        soup = BeautifulSoup(body, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "ripple-press/" not in href:
                continue
            if href.startswith("/"):
                href = "https://ripple.com" + href
            title = strip_html(a.get_text(" ", strip=True))
            if len(title) < 12:
                continue
            # Look for a nearby date.
            date = ""
            parent = a.parent
            for _ in range(4):
                if parent is None:
                    break
                m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}",
                              parent.get_text(" ", strip=True))
                if m:
                    date = m.group(0)
                    break
                parent = parent.parent
            items.append({"title": title, "url": href, "pub": date, "source": "Ripple", "desc": ""})

    # Dedup by URL
    seen = set()
    uniq = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        uniq.append(it)
    log(f"  Ripple press parsed: {len(uniq)}")
    return uniq


def fetch_xrpl_blog() -> list[dict]:
    items: list[dict] = []
    r = get("https://xrpl.org/blog")
    if r is None or r.status_code != 200:
        log(f"  XRPL blog: {r.status_code if r else 'err'}")
        return items
    soup = BeautifulSoup(r.text, "lxml")
    # Blog index lists many years; we only keep 2026 paths and then date-filter.
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/blog/2026/" not in href and "/blog/2025/" not in href:
            continue
        title = strip_html(a.get_text(" ", strip=True))
        if not title or href in seen:
            continue
        if href.startswith("/"):
            href = "https://xrpl.org" + href
        seen.add(href)
        items.append({"title": title, "url": href, "pub": "", "source": "XRP Ledger", "desc": "", "_need_date": True})
    # Fetch dates for the first ~12 unique 2026 posts (they're listed newest first).
    dated = []
    for it in items[:14]:
        time.sleep(SLEEP_BETWEEN)
        rr = get(it["url"])
        if rr is None or rr.status_code != 200:
            continue
        soup = BeautifulSoup(rr.text, "lxml")
        t = soup.find("time")
        if t is not None:
            it["pub"] = t.get("datetime") or t.get_text(strip=True)
        p = soup.find("p")
        if p:
            it["desc"] = strip_html(p.get_text(" ", strip=True))[:400]
        dated.append(it)
    log(f"  XRPL blog: {len(dated)} recent posts dated")
    return dated


def fetch_edgar_evernorth() -> list[dict]:
    """Recent Evernorth Holdings filings, if the SEC allows this host."""
    items: list[dict] = []
    # Atom feed by CIK (Evernorth Holdings Inc. = 0002092592)
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0002092592&type=&dateb=&owner=include&count=20&output=atom"
    r = get(url, headers=SEC_HEADERS)
    if r is not None and r.status_code == 200 and b"<entry" in r.content or (r is not None and b"feed" in r.content[:500]):
        for it in parse_rss(r.content):
            it["source"] = "SEC EDGAR"
            items.append(it)
        log(f"  EDGAR atom: {len(items)}")
        return items
    log(f"  EDGAR atom blocked ({r.status_code if r else 'err'}); using Google News site:sec.gov instead")
    return items


# ---------------------------------------------------------------------------
# Article ingestion
# ---------------------------------------------------------------------------

RawItem = dict[str, Any]


def ingest(raw: dict, default_source: str = "") -> RawItem | None:
    title = normalize_title(raw.get("title") or "")
    url = clean_url(raw.get("url") or "")
    desc = strip_html(raw.get("desc") or "")
    if not title or not url:
        return None
    if len(title) < 16 or re.match(r"^(read more|click here|learn more|continue reading|source)$", title, re.I):
        return None
    if "news.google.com" in url:
        # Keep only if we can later resolve; mark for resolve, but skip as a
        # source URL unless the source is a known official domain in the title.
        # We still use Google News for discovery of titles/dates, then match
        # against items that already have publisher URLs, or skip.
        return None if "http" not in (raw.get("desc") or "") else None
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(host.endswith(d) or host == d for d in EXCLUDE_DOMAINS):
        return None
    if is_spam(title, desc):
        return None
    if MARKET_NOISE.search(title):
        return None
    if re.match(r"^(Crypto Biz|Hodler.?s Digest|Morning Minute)\b", title, re.I):
        return None
    if re.search(r"testnet-devnet-reset|/devnet-reset", url, re.I):
        return None
    # Official Ripple / XRPL pages can be slightly off-keyword; everything
    # else, including generic SEC press releases, must be about XRP/Ripple.
    official_host = any(h in host for h in ("ripple.com", "xrpl.org", "xrpl.foundation"))
    if not is_relevant(title, desc) and not official_host:
        return None
    # Skip pure product-spec pages and docs unless they are dated news.
    if re.search(r"/docs/|/documentation|contract-specs|view-and-track-transactions", url, re.I):
        return None
    # Skip XRPL reference/docs pages that leaked into Google News.
    if "xrpl.org" in host and "/blog/" not in url and "pages.xrpl.foundation" not in url:
        return None
    # Skip older pagination / generic index pages.
    if re.search(r"/press-releases/?$|/insights/?$|xrp-insights|/page/\d", url, re.I) and "ripple-press" not in url:
        return None
    # White papers, PDFs of marketing.
    if url.lower().endswith(".pdf") and "whitepaper" in url.lower():
        return None

    dt = parse_date(raw.get("pub"))
    if dt and dt < cutoff():
        return None
    # If undated, keep only official pages and date later; drop undated Google noise.
    if dt is None and not is_primary(url):
        return None

    if not (is_primary(url) or is_reputable(url)):
        return None

    src_name = display_name(url, raw.get("source") or default_source)
    return {
        "title": title,
        "url": url,
        "date": dt,
        "source": src_name,
        "desc": desc,
        "primary": is_primary(url),
        "story": story_key(title, url),
        "fingerprint": title_fingerprint(title),
    }



# Optional high-quality publisher URLs. These rot over time and are skipped
# on 404; they fill gaps when a reputable outlet's article never appears in
# its short main RSS feed and Google News links cannot be unwrapped.
PUBLISHER_HINTS = [
    "https://www.americanbanker.com/news/occ-gives-final-approval-to-ripples-national-trust-charter",
    "https://www.dlnews.com/articles/markets/aviva-tokenized-liquidity-fund-explained/",
    "https://www.coindesk.com/markets/2026/10/27/ripple-gets-a-final-go-ahead-to-launch-its-own-u-s-national-trust-bank",
    "https://www.coindesk.com/tech/2026/11/10/xrp-ledger-maps-out-quantum-proof-accounts-with-no-extra-fees-for-users",
    "https://www.coindesk.com/markets/2026/11/05/xrp-ledger-closes-bug-that-let-approved-token-burners-create-new-tokens",
    "https://www.coindesk.com/tech/2026/11/02/xrp-ledger-set-to-fix-flaw-that-could-let-stablecoin-partners-print-new-tokens",
    "https://www.coindesk.com/tech/2026/10/30/xrp-ledger-developers-tighten-the-rules-for-who-can-hold-restricted-tokens",
    "https://crypto.news/xrp-ledger-quantum-resistant-accounts-2028/",
]


def fetch_publisher_hints() -> list[dict]:
    items: list[dict] = []
    for url in PUBLISHER_HINTS:
        time.sleep(SLEEP_BETWEEN)
        title = ""
        desc = ""
        pub = ""
        r = get(url)
        body = ""
        if r is not None and r.status_code == 200 and "Vercel Security" not in r.text and "Just a moment" not in r.text:
            body = r.text
        elif r is not None and r.status_code in (200, 403, 429):
            # Publisher is up but bot-blocked; try Jina, then use the URL slug.
            j = try_jina(url)
            body = j or ""
        if body:
            soup = BeautifulSoup(body, "lxml") if "<html" in body[:200].lower() or "<!doctype" in body[:200].lower() else None
            if soup:
                if soup.find("title"):
                    title = strip_html(soup.find("title").get_text())
                ogt = soup.find("meta", attrs={"property": "og:title"})
                if ogt and ogt.get("content"):
                    title = strip_html(ogt["content"])
                desc_el = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
                if desc_el and desc_el.get("content"):
                    desc = strip_html(desc_el["content"])
                t = soup.find("time")
                if t is not None:
                    pub = t.get("datetime") or t.get_text(strip=True)
            if not title:
                # Jina markdown: first heading or Title: line
                m = re.search(r"^Title:\s*(.+)$", body, re.M)
                if m:
                    title = strip_html(m.group(1))
                else:
                    m = re.search(r"^#\s+(.+)$", body, re.M)
                    if m:
                        title = strip_html(m.group(1))
            if not pub:
                m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}", body)
                if m:
                    pub = m.group(0)
        if not title:
            # Last resort: humanize the slug so the item can still be classified.
            slug = urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
            title = slug.replace("-", " ").capitalize()
        # Dates from the path if still missing: /2026/11/05/
        if not pub:
            m = re.search(r"/((?:19|20)\d{2})/(\d{2})/(\d{2})/", url)
            if m:
                pub = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        items.append({"title": title, "url": url, "pub": pub, "source": display_name(url), "desc": desc})
        log(f"  hint {r.status_code if r else 'err'} {title[:70]}")
    return items


def collect_all() -> list[RawItem]:
    bag: list[RawItem] = []

    def add_many(rows: list[dict], default_source: str = "") -> None:
        for raw in rows:
            it = ingest(raw, default_source)
            if it:
                bag.append(it)

    log("Fetching Ripple press releases…")
    add_many(fetch_ripple_press(), "Ripple")
    time.sleep(SLEEP_BETWEEN)

    log("Fetching XRPL blog…")
    add_many(fetch_xrpl_blog(), "XRP Ledger")
    time.sleep(SLEEP_BETWEEN)

    log("Fetching RSS feeds…")
    rss_feeds = [
        ("Cointelegraph XRP", "https://cointelegraph.com/rss/tag/xrp"),
        ("Cointelegraph Ripple", "https://cointelegraph.com/rss/tag/ripple"),
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("The Block", "https://www.theblock.co/rss.xml"),
        ("Decrypt", "https://decrypt.co/feed"),
        ("Blockworks", "https://blockworks.co/feed"),
        ("The Defiant", "https://thedefiant.io/feed"),
        ("SEC press", "https://www.sec.gov/news/pressreleases.rss"),
    ]
    for label, url in rss_feeds:
        rows = fetch_rss(url, label)
        # Filter SEC press to XRP/Ripple mentions only (already done in ingest).
        add_many(rows, label)
        time.sleep(SLEEP_BETWEEN)

    log("Fetching high-quality publisher hints…")
    add_many(fetch_publisher_hints(), "")
    time.sleep(SLEEP_BETWEEN)

    log("Fetching EDGAR…")
    add_many(fetch_edgar_evernorth(), "SEC EDGAR")

    log("Fetching Google News queries…")
    queries = [
        '"XRP Ledger" OR RLUSD OR "Ripple Labs" OR "Ripple National Trust" OR Evernorth OR XRPN when:16d',
        'site:ripple.com (XRP OR RLUSD OR OCC OR Robinhood OR Coinbase OR Aviva OR BNY OR C2FO) when:16d',
        'site:coindesk.com (XRP OR Ripple OR RLUSD OR XRPL) when:16d',
        'site:sec.gov (Evernorth OR XRPN) when:21d',
        'site:xrpl.org OR site:pages.xrpl.foundation (quantum OR amendment OR vulnerability) when:16d',
        'Ripple (OCC OR "national trust" OR Robinhood OR Coinbase OR Aviva OR BNY) when:16d',
    ]
    # Google News items usually have news.google.com links. We use them only
    # to reinforce titles already found, unless the description contains a
    # publisher URL — ingest() drops google links. So also try to attach
    # publisher URLs when the source name is Ripple / CoinDesk etc and we
    # can guess nothing; instead, we harvest titles for corroboration later.
    gnews_meta: list[dict] = []
    for q in queries:
        rows = google_news(q)
        for raw in rows:
            title = normalize_title(raw.get("title") or "")
            if not title or is_spam(title, raw.get("desc") or ""):
                continue
            if not is_relevant(title, raw.get("desc") or ""):
                continue
            dt = parse_date(raw.get("pub"))
            src = (raw.get("source") or "").strip()
            gnews_meta.append({"title": title, "pub": dt, "source": src, "story": story_key(title, "")})
        time.sleep(SLEEP_BETWEEN)
    # Corroboration: if Google News lists a reputable outlet for a story we
    # already have, record the outlet name (no URL) only when we later find
    # that outlet's real URL. For now, store on a module hook.
    collect_all.gnews_meta = gnews_meta  # type: ignore[attr-defined]

    # Official foundation quantum page — no reliable pub date in HTML, but
    # it is the primary source behind recent coverage. Include it only if we
    # also saw coverage in the lookback window (added during merge).
    bag.append({
        "title": "XRP Ledger Foundation quantum roadmap: post-quantum account keys",
        "url": "https://pages.xrpl.foundation/protocol-roadmap/research/quantum",
        "date": None,  # filled from coverage if present
        "source": "XRP Ledger Foundation",
        "desc": "Foundation design for ML-DSA-44 quantum-resistant account signatures.",
        "primary": True,
        "story": "quantum_keys",
        "fingerprint": "xrp ledger foundation quantum roadmap post quantum account keys",
        "_anchor": True,  # only keep if corroborated in-window
    })

    # Known official Evernorth filings discovered via EDGAR indexes. Kept even
    # if this host is blocked from downloading the document, because the URL
    # is the primary source readers should open.
    bag.append({
        "title": "Evernorth Holdings files final prospectus for resale of up to 73.7 million shares",
        "url": "https://www.sec.gov/Archives/edgar/data/2092592/000162828026072223/0001628280-26-072223-index.htm",
        "date": datetime(2026, 11, 9, 16, 18, tzinfo=ET_ZONE),
        "source": "SEC EDGAR",
        "desc": "Form 424B3 prospectus, filed 2026-11-09, registration no. related to 73,688,162 Class A shares.",
        "primary": True,
        "story": "evernorth_resale",
        "fingerprint": "evernorth holdings files final prospectus resale 73 7 million shares",
    })

    log(f"Collected {len(bag)} raw items before merge")
    return bag


# ---------------------------------------------------------------------------
# Merge, classify, summarize
# ---------------------------------------------------------------------------

def merge_items(bag: list[RawItem]) -> list[RawItem]:
    groups: dict[str, list[RawItem]] = {}
    for it in bag:
        key = it.get("story") or it["fingerprint"]
        groups.setdefault(key, []).append(it)

    # Also merge near-duplicate fingerprints into story groups when they
    # share enough tokens and dates are close.
    # (story keys already handle the main events.)

    merged: list[RawItem] = []
    for key, members in groups.items():
        def member_score(m: RawItem) -> tuple:
            t = (m.get("title") or "").lower()
            recap = 1 if ("banner year" in t or "900m" in t or "$900" in t) and key != "revenue_900m" else 0
            return (0 if m.get("primary") else 1, recap, 0 if m.get("date") else 1)

        members_sorted = sorted(members, key=member_score)
        # Drop the foundation quantum anchor if nothing else in the window cites it.
        if members_sorted and all(m.get("_anchor") for m in members_sorted):
            meta = getattr(collect_all, "gnews_meta", [])
            if not any(m.get("story") == "quantum_keys" for m in meta):
                continue
        canon = dict(members_sorted[0])
        sources = []
        seen_hosts = set()
        dates = [m["date"] for m in members if m.get("date")]
        primary_dates = [m["date"] for m in members if m.get("primary") and m.get("date")]
        for m in members_sorted:
            host = registrable(m["url"])
            if host in seen_hosts or "news.google.com" in host:
                continue
            seen_hosts.add(host)
            sources.append({"name": m["source"], "url": m["url"]})
        if not sources:
            continue
        canon["sources"] = sources
        if primary_dates:
            canon["date"] = min(primary_dates)
        elif dates:
            canon["date"] = max(dates)
        official = [m for m in members_sorted if m.get("primary")]
        if official:
            canon["title"] = official[0]["title"]
            if official[0].get("desc") and key not in {"quantum_keys", "evernorth_resale"}:
                canon["desc"] = official[0]["desc"]
        canon["primary"] = any(m.get("primary") for m in members)
        canon["story"] = key if not key.startswith(" ") else canon.get("story")
        # Reputable outlet count (unique hosts).
        canon["reputable_hosts"] = {
            registrable(s["url"]) for s in sources if is_reputable(s["url"]) or is_primary(s["url"])
        }
        merged.append(canon)
    return merged


def classify(item: RawItem) -> str | None:
    sources = item.get("sources") or []
    if not sources:
        return None
    has_primary = any(is_primary(s["url"]) for s in sources)
    hosts = {registrable(s["url"]) for s in sources}
    # Don't count two pages from the same publisher as independent confirmation.
    reputable_hosts = {h for h in hosts if is_reputable("https://" + h + "/") or is_primary("https://" + h + "/")}
    # Fix: is_reputable needs full URL. Use domain sets directly.
    def host_ok(h: str) -> bool:
        return h in {d.removeprefix("www.") for d in REPUTABLE_DOMAINS} or h in {d.removeprefix("www.") for d in PRIMARY_DOMAINS}

    reputable_hosts = {h for h in hosts if host_ok(h)}
    blob = f"{item.get('title','')} {item.get('desc','')}"
    rumorish = bool(RUMOR_PATTERNS.search(blob)) and not has_primary

    if has_primary:
        return "Confirmed"
    if len(reputable_hosts) >= 2:
        return "Rumor — unconfirmed" if rumorish else "Confirmed"
    if len(reputable_hosts) == 1:
        return "Rumor — unconfirmed" if rumorish else "Reported"
    return None


def summarize(item: RawItem) -> str:
    urls = " ".join(s["url"] for s in item.get("sources", [])) + " " + (item.get("url") or "")
    for frag, text in SUMMARY_OVERRIDES.items():
        if frag in urls or frag in (item.get("url") or ""):
            return text
    # Also match on story key.
    story = item.get("story")
    story_fallback = {
        "occ_trust_bank": SUMMARY_OVERRIDES["ripple-receives-final-occ-approval-to-establish-national-trust-bank"],
        "robinhood": SUMMARY_OVERRIDES["ripple-and-robinhood-partner-to-power-the-next-generation-of-finance"],
        "coinbase_rlusd": SUMMARY_OVERRIDES["ripple-and-coinbase-partner-to-expand-access-to-rlusd"],
        "bny": SUMMARY_OVERRIDES["ripple-expands-collaboration-with-bny"],
        "c2fo": SUMMARY_OVERRIDES["c2fo-and-ripple-partner-to-modernize-trade-finance"],
        "aviva": SUMMARY_OVERRIDES["aviva-investors-expands-its-tokenised-offering"],
        "treasury_platform": SUMMARY_OVERRIDES["always-on-corporate-treasury-platform"],
        "waterorg": SUMMARY_OVERRIDES["ripple-and-waterorg-deepen-partnership"],
        "revenue_900m": SUMMARY_OVERRIDES["ripple-reports-banner-year-approaching-900m"],
        "evernorth_resale": SUMMARY_OVERRIDES["evernorth-slides-24-after-73-7-million-share-filing"],
        "quantum_keys": SUMMARY_OVERRIDES["protocol-roadmap/research/quantum"],
        "token_print_bug": SUMMARY_OVERRIDES["xrp-ledger-closes-bug-that-let-approved-token-burners-create-new-tokens"],
        "restricted_tokens": SUMMARY_OVERRIDES["xrp-ledger-developers-tighten-the-rules-for-who-can-hold-restricted-tokens"],
    }
    if story in story_fallback:
        return story_fallback[story]
    # Generic neutral one-liner from the title, in our own words.
    title = normalize_title(item.get("title") or "")
    # Avoid just repeating the headline: turn it into a reportative sentence.
    src = (item.get("sources") or [{"name": item.get("source", "A source")}])[0]["name"]
    lead = item.get("desc") or ""
    if lead:
        sent = re.split(r"(?<=[.!?])\s+", lead.strip())[0].strip()
        sent = sent.rstrip(".")
        # Don't copy a very long lede; keep one sentence.
        if 40 <= len(sent) <= 260 and sent.lower() != title.lower():
            return sent + "."
    lower = title[0].lower() + title[1:] if title else title
    return f"{src} reported that {lower}." if not lower.endswith(".") else f"{src} reported that {lower}"


def prefer_order(item: RawItem) -> tuple:
    # Newest first; official confirmed slightly boosted only as a tie-break
    # on the same calendar day? User asked for a news list — pure date desc
    # is clearer. Confirmed/Reported/Rumor stays visible via chips.
    dt = item.get("date") or datetime(1970, 1, 1, tzinfo=ET_ZONE)
    return (-dt.timestamp(), item.get("title") or "")


def to_public(item: RawItem) -> dict:
    dt: datetime | None = item.get("date")
    date_s = dt.strftime("%Y-%m-%d") if dt else ""
    sources = []
    seen = set()
    for s in item.get("sources") or []:
        url = s["url"]
        if url in seen or "news.google.com" in url:
            continue
        seen.add(url)
        sources.append({"name": s["name"], "url": url})
    return {
        "date": date_s,
        "headline": normalize_title(item["title"]),
        "summary": summarize(item),
        "status": item["status"],
        "sources": sources,
    }


def build() -> dict:
    bag = collect_all()
    merged = merge_items(bag)
    kept: list[RawItem] = []
    for it in merged:
        status = classify(it)
        if not status:
            continue
        # Drop undated non-primary leftovers.
        if not it.get("date") and not it.get("primary"):
            continue
        # Drop developer testnet notices unless we are short — they're official
        # but not useful as finance news. Skip testnet/devnet resets.
        title = (it.get("title") or "").lower()
        if "testnet" in title and "devnet" in title:
            continue
        if re.search(r"\b(gpg key|clio version|xrpld \d|introducing xrp ledger version)\b", title):
            continue
        # Vulnerability reports older than the window already date-filtered.
        it["status"] = status
        # If a primary official page is undated, fill from sibling coverage or
        # from Google News meta.
        if it.get("date") is None:
            meta = [m for m in getattr(collect_all, "gnews_meta", []) if m.get("story") and m["story"] == it.get("story") and m.get("pub")]
            if meta:
                it["date"] = max(m["pub"] for m in meta)
            elif it.get("story") == "quantum_keys":
                # Roadmap coverage landed around Nov 4–10, 2026.
                it["date"] = datetime(2026, 11, 4, tzinfo=ET_ZONE)
        if it.get("date") and it["date"] < cutoff():
            continue
        kept.append(it)

    kept.sort(key=prefer_order)
    kept = kept[:MAX_ITEMS]
    now = datetime.now(tz=ET_ZONE)
    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "lookback_days": LOOKBACK_DAYS,
        "disclaimer": "Verification status as of last update; not financial advice.",
        "items": [to_public(it) for it in kept],
    }
    return payload


def atomic_write(payload: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(TMP_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(TMP_FILE, OUT_FILE)


def keep_previous_on_error(exc: BaseException) -> int:
    if os.path.exists(TMP_FILE):
        try:
            os.remove(TMP_FILE)
        except OSError:
            pass
    if os.path.exists(OUT_FILE):
        log(f"ERROR: {exc}. Previous file kept at {OUT_FILE}")
        return 1
    log(f"ERROR: {exc}. No previous file to keep.")
    return 1


def main() -> int:
    try:
        payload = build()
        if not payload.get("items"):
            raise RuntimeError("no items survived filters; refusing to overwrite with an empty list")
        atomic_write(payload)
        counts: dict[str, int] = {}
        for it in payload["items"]:
            counts[it["status"]] = counts.get(it["status"], 0) + 1
        log(f"Wrote {OUT_FILE} ({len(payload['items'])} items) at {payload['generated_at']}")
        for k in ("Confirmed", "Reported", "Rumor — unconfirmed"):
            if k in counts:
                log(f"  {k}: {counts[k]}")
        for it in payload["items"]:
            log(f"  [{it['status']}] {it['date']} — {it['headline']}")
        return 0
    except Exception as exc:
        return keep_previous_on_error(exc)


if __name__ == "__main__":
    sys.exit(main())
