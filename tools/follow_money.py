#!/usr/bin/env python3
"""Follow the Money: daily public-disclosure feed for follow_money.html.

Fetches free, public, official sources and writes data/follow_money.json
(schema 1, the same shape the page already renders):

  congress  U.S. House Clerk PTR index (yearly ZIP) + electronic PTR PDFs
  insiders  SEC EDGAR daily form index -> Form 4 XML, code P open-market buys
  funds     SEC EDGAR submissions API -> latest two 13F-HR information tables
  crypto    CoinGecko public-treasury endpoint (company BTC/ETH holdings)
  social    no verified source yet -> "coming soon" card (no names)

Rules: polite per-host rate limits, SEC User-Agent with contact, every row
links its source, nothing invented. If a section fails, the previous day's
section is kept and marked stale. Cache lives outside the site repo.

Usage:
  python3 tools/follow_money.py            # fetch everything, write JSON
  python3 tools/follow_money.py --check    # validate data/follow_money.json only
  python3 tools/follow_money.py --only insiders,funds
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "follow_money.json"
CACHE = Path(os.environ.get("FM_CACHE", "/workspace/sift_follow_money/cache"))
UA = "SIFT research siftstrategy@gmail.com"
NFA = "Research only, not financial advice. Place any trade yourself at your own broker."

SECTION_IDS = ("congress", "funds", "insiders", "crypto", "social")
CARD_FIELDS = ("id", "sample", "entity", "who", "what", "action", "detail", "trade_date",
               "public_date", "why", "confidence", "caveats", "tickers", "weights")
SECTION_FIELDS = ("id", "title", "summary", "blurb", "source_name", "source_url",
                  "as_of_label", "public_label", "lag", "cards")
BANNED_KEYS = {"cagr", "return_pct", "sharpe", "backtest", "win_rate", "total_return", "performance"}

FUNDS = (  # curated 13F filers (CIK, display name)
    (1067983, "Berkshire Hathaway (Warren Buffett)"),
    (1336528, "Pershing Square (Bill Ackman)"),
    (1649339, "Scion Asset Management (Michael Burry)"),
    (1350694, "Bridgewater Associates (Ray Dalio's firm)"),
    (1697748, "ARK Investment Management (Cathie Wood)"),
    (1536411, "Duquesne Family Office (Stanley Druckenmiller)"),
    (1656456, "Appaloosa (David Tepper)"),
    (1061768, "Baupost Group (Seth Klarman)"),
    (1029160, "Soros Fund Management"),
    (1167483, "Tiger Global Management"),
)

LOG: list[str] = []


def log(msg: str) -> None:
    LOG.append(msg)
    print("follow_money: " + msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- HTTP ----
_last: dict[str, float] = {}
_lock = threading.Lock()
GAP = {"www.sec.gov": 0.13, "data.sec.gov": 0.13, "efts.sec.gov": 0.2,
       "disclosures-clerk.house.gov": 1.0, "api.coingecko.com": 3.0, "api.openfigi.com": 2.6}


def http(url: str, data: bytes | None = None, headers: dict | None = None, tries: int = 3) -> bytes:
    host = url.split("/")[2]
    for attempt in range(tries):
        with _lock:  # reserve the next slot for this host (thread-safe, keeps under SEC's 10 req/s)
            slot = max(time.time(), _last.get(host, 0) + GAP.get(host, 1.0))
            _last[host] = slot
        if slot > time.time():
            time.sleep(slot - time.time())
        h = {"User-Agent": UA, "Accept-Encoding": "identity"}
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1) if e.code in (429, 503) else 2)
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2)
    raise RuntimeError("unreachable")


def http_json(url: str, **kw):
    return json.loads(http(url, **kw))


def cache_json(name: str, default):
    p = CACHE / name
    if p.is_file():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return default


def save_cache(name: str, obj) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = CACHE / (name + ".tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(CACHE / name)


# -------------------------------------------------------------- helpers ----
def money(v: float) -> str:
    v = float(v)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= div:
            s = f"{v / div:.1f}".rstrip("0").rstrip(".")
            return f"${s}{unit}"
    return f"${v:,.0f}"


def short_range(txt: str) -> str:
    nums = [int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", txt)]
    if "over" in txt.lower() and nums:
        return "Over " + money(nums[0])
    if len(nums) >= 2:
        lo = nums[0] - 1 if nums[0] % 1000 == 1 else nums[0]
        return money(lo) + "–" + money(nums[1])
    return txt.strip()


def sic_sector(code) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return ""
    if c in range(2830, 2837) or c in range(3841, 3852) or c in range(8000, 8100) or c == 5122:
        return "Health care"
    if c in range(3570, 3580) or c in range(3670, 3680) or c in range(7370, 7380) or c in (3661, 3663, 3674, 3576):
        return "Technology"
    if c in (1311, 1381, 1382, 1389, 2911, 2990, 4922, 4923, 4924, 5171, 5172, 6792):
        return "Energy"
    if c in range(1000, 1500) or c in range(2600, 2700) or c in range(2800, 2830) or c in range(2840, 2900) or c in range(3300, 3400):
        return "Materials"
    if c in range(3710, 3717) or c in range(5500, 5600):
        return "Autos"
    if c in range(4800, 4900) or c in range(7810, 7850) or c in range(2710, 2742):
        return "Communications"
    if c in range(4900, 5000):
        return "Utilities"
    if c in (6798,) or c in range(6500, 6600):
        return "Real estate"
    if c in range(6000, 6800):
        return "Financials"
    if c in range(5000, 6000) or c in range(2000, 2200) or c in range(7000, 7100) or c in range(5800, 5900):
        return "Consumer"
    if c in range(3720, 3730) or c in range(3760, 3770) or c in range(3810, 3813):
        return "Aerospace & defense"
    if c in range(1500, 1800) or c in range(3400, 3570) or c in range(3580, 3670) or c in range(3680, 3840) or c in range(4000, 4800):
        return "Industrials"
    if c in range(7000, 9000):
        return "Services"
    return "Other"


class Sectors:
    """Ticker/CIK -> broad sector, from SEC company_tickers.json + submissions SIC (cached)."""

    def __init__(self):
        self.map = cache_json("sic.json", {})
        self.tick = None
        self.budget = 250

    def _tickers(self):
        if self.tick is None:
            p = CACHE / "company_tickers.json"
            fresh = p.is_file() and time.time() - p.stat().st_mtime < 7 * 86400
            try:
                if not fresh:
                    p.write_bytes(http("https://www.sec.gov/files/company_tickers.json"))
                raw = json.loads(p.read_text())
                self.tick = {v["ticker"].upper(): int(v["cik_str"]) for v in raw.values()}
            except Exception as e:
                log(f"company_tickers failed: {e}")
                self.tick = {}
        return self.tick

    def cik_for(self, ticker: str):
        t = (ticker or "").upper().replace(".", "-")
        return self._tickers().get(t)

    def for_cik(self, cik) -> str:
        if not cik:
            return ""
        key = str(int(cik))
        hit = self.map.get(key)
        if hit and time.time() - hit.get("t", 0) < 60 * 86400:
            return hit["sector"]
        if self.budget <= 0:
            return hit["sector"] if hit else ""
        self.budget -= 1
        try:
            d = http_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
            sector = sic_sector(d.get("sic"))
            if (d.get("sicDescription") or "").upper().startswith("UNKNOWN"):
                sector = ""
        except Exception:
            sector = ""
        self.map[key] = {"sector": sector, "t": time.time()}
        return sector

    def for_ticker(self, ticker: str) -> str:
        return self.for_cik(self.cik_for(ticker))

    def save(self):
        save_cache("sic.json", self.map)


def card(**kw) -> dict:
    base = {"sample": False, "weights": [], "confidence": "", "caveats": "", "why": ""}
    base.update(kw)
    return base


# ------------------------------------------------------------- CONGRESS ----
TX_RE = re.compile(r"\s(P|S \(partial\)|S|E)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(.*)$")
PER_FILING = 6  # keep one big filer from filling the whole list; the PDF link has the rest
OWNERS = {"SP": "spouse", "JT": "joint", "DC": "dependent child"}


def parse_ptr(text: str) -> list[dict]:
    rows = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = TX_RE.search(lines[i])
        if not m:
            i += 1
            continue
        asset = lines[i][: m.start()].strip()
        amount = m.group(4).strip()
        j = i + 1
        while j < len(lines) and lines[j].strip() and not TX_RE.search(lines[j]):
            seg = lines[j]
            if re.match(r"^\s*(F\s+S|S\s+O|D\s*:|C\s*:|Filing|Subholding|Description|Comments)", seg.strip()[:12]) or re.search(r"\b(F      S|S           O)\b", seg):
                break
            left = seg[: m.start()].strip() if len(seg) > m.start() else seg.strip()
            right = seg[m.start():].strip() if len(seg) > m.start() else ""
            if left:
                asset += " " + left
            if right and amount.endswith("-"):
                amount += " " + right
            j += 1
        owner = ""
        om = re.match(r"^(SP|JT|DC)\s+(.*)$", asset)
        if om:
            owner, asset = OWNERS[om.group(1)], om.group(2)
        tm = re.search(r"\(([A-Z][A-Z0-9.\-]{0,6})\)", asset)
        km = re.search(r"\[([A-Z]{2})\]", asset)
        rows.append({
            "asset": re.sub(r"\s+", " ", re.sub(r"\[[A-Z]{2}\]", "", asset)).strip(),
            "ticker": tm.group(1) if tm else "",
            "kind": km.group(1) if km else "",
            "type": m.group(1),
            "trade_date": m.group(2),
            "notify_date": m.group(3),
            "amount": re.sub(r"\s+", " ", amount),
            "owner": owner,
        })
        i = j
    return rows


def fetch_congress(sec: Sectors) -> dict:
    year = dt.date.today().year
    zurl = f"https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
    z = zipfile.ZipFile(io.BytesIO(http(zurl)))
    root = ET.fromstring(z.read(f"{year}FD.xml"))
    ptrs = []
    for m in root:
        if m.findtext("FilingType") != "P":
            continue
        try:
            fd = dt.datetime.strptime(m.findtext("FilingDate"), "%m/%d/%Y").date()
        except Exception:
            continue
        doc = m.findtext("DocID") or ""
        name = " ".join(x for x in (m.findtext("First"), m.findtext("Last")) if x)
        name = re.sub(r"\s+(Mr|Mrs|Ms|Dr)\.?(?=\s|$)", "", name).strip()
        ptrs.append({"doc": doc, "filed": fd.isoformat(), "name": name, "dist": m.findtext("StateDst") or ""})
    ptrs.sort(key=lambda p: (p["filed"], p["doc"]), reverse=True)
    cache = cache_json("house_ptr.json", {})
    electronic = [p for p in ptrs if p["doc"].startswith("2")]  # 8-digit 2xxxxxxx = e-filed; others are scanned paper
    paper = [p for p in ptrs[:60] if not p["doc"].startswith("2")]
    picked, fetched = [], 0
    for p in electronic[:45]:
        url = f"https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{p['doc']}.pdf"
        if p["doc"] not in cache:
            try:
                pdf = http(url)
                with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
                    f.write(pdf)
                    f.flush()
                    txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=60).stdout
                cache[p["doc"]] = parse_ptr(txt)
                fetched += 1
            except Exception as e:
                log(f"house PTR {p['doc']} failed: {e}")
                continue
        picked.append((p, url, cache[p["doc"]]))
    save_cache("house_ptr.json", cache)
    cards = []
    for p, url, rows in picked:
        usable = [(n, r) for n, r in enumerate(rows) if r["ticker"] and r["kind"] in ("ST", "EF", "OP", "")]
        usable.sort(key=lambda nr: dt.datetime.strptime(nr[1]["trade_date"], "%m/%d/%Y"), reverse=True)
        for n, r in usable[:PER_FILING]:
            act = {"P": "buy", "S": "sell", "S (partial)": "partial sell", "E": "exchange"}[r["type"]]
            td = dt.datetime.strptime(r["trade_date"], "%m/%d/%Y").date().isoformat()
            rng = short_range(r["amount"])
            who = f"Rep. {p['name']} ({p['dist'][:2]}-{p['dist'][2:]})" if p["dist"] else f"Rep. {p['name']}"
            opt = " (options)" if r["kind"] == "OP" else ""
            sector = sec.for_ticker(r["ticker"])
            verb = {"buy": "BUY", "sell": "SELL", "partial sell": "SELL (partial)", "exchange": "EXCHANGE"}[act]
            owner = f" Owner: {r['owner']}." if r["owner"] else ""
            cards.append(card(
                id=f"house-{p['doc']}-{n}", entity=who, who=who, what=r["ticker"], action=act + opt,
                detail=f"{r['asset']}. Amount range {r['amount']}.{owner}" + (f" This filing lists {len(usable)} trades; the newest {PER_FILING} are shown." if len(usable) > PER_FILING else ""),
                trade_date=td, public_date=p["filed"], tickers=[r["ticker"]], sector=sector,
                why="Restated from the member's periodic transaction report (STOCK Act).",
                confidence="Primary filing. Amounts are ranges, not exact sizes.",
                caveats=f"Filed {(dt.date.fromisoformat(p['filed']) - dt.date.fromisoformat(td)).days} days after the trade. Parsed from the PDF; check the filing.",
                source_url=url,
                copy_line=f"{verb} {r['ticker']}{opt}, {rng}, {who}, traded {td} (filed {p['filed']})",
                csv={"member": who, "ticker": r["ticker"], "action": act + opt, "amount_range": r["amount"],
                     "trade_date": td, "filed_date": p["filed"], "sector": sector, "source_url": url},
            ))
    cards.sort(key=lambda c: (c["public_date"], c["trade_date"]), reverse=True)
    cards = cards[:60]
    if not cards:
        raise RuntimeError("no parsable House PTR rows")
    log(f"congress: {len(picked)} PTRs ({fetched} new), {len(cards)} rows, {len(paper)} recent paper filings skipped")
    newest = max(c["public_date"] for c in cards)
    return {"cards": cards, "as_of": newest,
            "summary": f"{len(cards)} House trades from the latest e-filed reports. Newest filing {newest}.",
            "note": f"{len(paper)} recent scanned paper filings are not parsed. Senate eFD is not connected yet."}


# ------------------------------------------------------------- INSIDERS ----
def business_days(n: int) -> list[dt.date]:
    out, d = [], dt.date.today()
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return out


def parse_form4(xml: str) -> dict | None:
    m = re.search(r"<ownershipDocument>.*</ownershipDocument>", xml, re.S)
    if not m:
        return None
    try:
        r = ET.fromstring(m.group(0))
    except ET.ParseError:
        return None
    buys = []
    for t in r.findall("./nonDerivativeTable/nonDerivativeTransaction"):
        if (t.findtext("./transactionCoding/transactionCode") or "").strip() != "P":
            continue
        try:
            sh = float(t.findtext("./transactionAmounts/transactionShares/value") or 0)
            px = float(t.findtext("./transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            continue
        if (t.findtext("./transactionAmounts/transactionAcquiredDisposedCode/value") or "A").strip() != "A":
            continue
        buys.append({"shares": sh, "price": px, "date": (t.findtext("./transactionDate/value") or "")[:10]})
    if not buys:
        return {"p": False}
    if (r.findtext("./aff10b5One") or "").strip().lower() in ("1", "true"):
        return {"p": False, "plan": True}
    owners = []
    for o in r.findall("./reportingOwner"):
        rel = o.find("reportingOwnerRelationship")
        role = []
        if rel is not None:
            if (rel.findtext("isDirector") or "").strip() in ("1", "true"):
                role.append("Director")
            if (rel.findtext("isOfficer") or "").strip() in ("1", "true"):
                role.append((rel.findtext("officerTitle") or "Officer").strip())
            if (rel.findtext("isTenPercentOwner") or "").strip() in ("1", "true"):
                role.append("10% owner")
        owners.append({"name": (o.findtext("./reportingOwnerId/rptOwnerName") or "").strip(), "role": ", ".join(role)})
    return {
        "p": True,
        "issuer": (r.findtext("./issuer/issuerName") or "").strip(),
        "issuer_cik": (r.findtext("./issuer/issuerCik") or "").strip(),
        "ticker": (r.findtext("./issuer/issuerTradingSymbol") or "").strip().upper(),
        "owners": owners,
        "shares": sum(b["shares"] for b in buys),
        "value": sum(b["shares"] * b["price"] for b in buys),
        "first": min(b["date"] for b in buys), "last": max(b["date"] for b in buys),
    }


def fetch_insiders(sec: Sectors, days: int = 10) -> dict:
    cache = cache_json("form4.json", {})  # accession -> parsed or {"p": False}
    done_days = set(cache_json("form4_days.json", []))
    want = business_days(days)
    cutoff = (dt.date.today() - dt.timedelta(days=21)).isoformat()
    fetched, failed = 0, 0
    for day in want:
        ds = day.strftime("%Y%m%d")
        if ds in done_days and day != dt.date.today():
            continue
        q = (day.month - 1) // 3 + 1
        url = f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{q}/form.{ds}.idx"
        try:
            idx = http(url).decode("latin-1")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                continue  # holiday or not yet posted
            raise
        accs = {}
        for line in idx.splitlines():
            if line.startswith("4 ") or line.startswith("4/A "):
                if line.startswith("4/A"):
                    continue
                path = line.split()[-1]
                acc = path.rsplit("/", 1)[-1][:-4]
                accs.setdefault(acc, path)
        day_ok = True

        def one(item):
            acc, path = item
            try:
                return acc, path, parse_form4(http("https://www.sec.gov/Archives/" + path).decode("utf-8", "replace"))
            except Exception:
                return acc, path, "ERR"

        todo = [(a, p) for a, p in accs.items() if a not in cache]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for acc, path, doc in pool.map(one, todo):
                if doc == "ERR":
                    failed += 1
                    day_ok = False
                    continue
                fetched += 1
                if doc is None:
                    doc = {"p": False}
                doc["filed"] = day.isoformat()
                doc["path"] = path
                cache[acc] = doc if doc.get("p") else {"p": False, "filed": day.isoformat()}
        save_cache("form4.json", cache)
        log(f"insiders: {day} done, {len(todo)} new filings, {fetched} fetched so far")
        if day_ok and day != dt.date.today():
            done_days.add(ds)
    cache = {k: v for k, v in cache.items() if v.get("filed", "9") >= cutoff}
    save_cache("form4.json", cache)
    save_cache("form4_days.json", sorted(d for d in done_days if d >= cutoff.replace("-", "")))
    since = want[-1].isoformat()
    buys = [(k, v) for k, v in cache.items() if v.get("p") and v["filed"] >= since and v.get("value", 0) > 0 and v.get("ticker") not in ("", "NONE", "N/A")]
    buys.sort(key=lambda kv: (kv[1]["value"], kv[1]["filed"]), reverse=True)
    # Joint filers (a fund and its GP, a trust and its trustee) file the same purchase separately: merge them.
    merged, seen = [], {}
    for acc, v in buys:
        key = (v["ticker"], round(v["shares"]), round(v["value"]), v["first"], v["last"])
        if key in seen:
            prev = seen[key]
            names = {o["name"] for o in prev["owners"]}
            prev["owners"] += [o for o in v["owners"] if o["name"] not in names]
            continue
        v = dict(v, owners=list(v["owners"]))
        seen[key] = v
        merged.append((acc, v))
    buys = merged
    cards = []
    for acc, v in buys[:30]:
        cik = v["path"].split("/")[2]
        src = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm"
        owner = v["owners"][0] if v["owners"] else {"name": "Unknown", "role": ""}
        names = "; ".join(o["name"] for o in v["owners"])
        role = owner["role"] or "Reporting owner"
        avg = v["value"] / v["shares"] if v["shares"] else 0
        sector = sec.for_cik(v.get("issuer_cik"))
        who = f"{owner['name']}, {role}"
        dates = v["first"] if v["first"] == v["last"] else f"{v['first']} to {v['last']}"
        cards.append(card(
            id=f"f4-{acc}", entity=v["issuer"] + (f" ({v['ticker']})" if v["ticker"] else ""), who=who,
            what=v["ticker"], action="open-market buy",
            detail=f"{v['shares']:,.0f} shares, about {money(v['value'])} at an average {avg:,.2f} per share. Reporting owner(s): {names}.",
            trade_date=dates, public_date=v["filed"], tickers=[v["ticker"]], sector=sector,
            why="Insiders buying their own company's stock with their own money on the open market (code P).",
            confidence="Primary filing (SEC Form 4). Value = shares × reported price.",
            caveats="Not a 10b5-1 plan purchase. One filing can bundle several fills. 10% owners are often funds, not executives. A buy at a round price near a listing date may be an IPO or private-placement allocation, not an open-market fill.",
            source_url=src,
            copy_line=f"BUY {v['ticker']}, {money(v['value'])} ({v['shares']:,.0f} sh @ ${avg:,.2f}), {who} at {v['issuer']}, traded {dates} (filed {v['filed']})",
            csv={"company": v["issuer"], "ticker": v["ticker"], "insider": names, "role": role, "shares": round(v["shares"]),
                 "avg_price": round(avg, 4), "value_usd": round(v["value"]), "trade_date": dates, "filed_date": v["filed"],
                 "sector": sector, "source_url": src},
        ))
    if not cards:
        raise RuntimeError("no Form 4 code-P rows")
    log(f"insiders: {fetched} new Form 4s fetched ({failed} failed), {len(buys)} distinct code-P purchases since {since}, {len(cards)} shown")
    return {"cards": cards, "as_of": max(c["public_date"] for c in cards),
            "summary": f"Top {len(cards)} open-market buys by dollar value, filed {since} to {max(c['public_date'] for c in cards)}.",
            "note": ""}


# ---------------------------------------------------------------- FUNDS ----
def figi_tickers(cusips: list[str]) -> dict:
    cache = cache_json("figi.json", {})
    need = [c for c in dict.fromkeys(cusips) if c not in cache]
    for i in range(0, len(need), 10):
        chunk = need[i:i + 10]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk]).encode()
        try:
            res = http_json("https://api.openfigi.com/v3/mapping", data=body, headers={"Content-Type": "application/json"})
        except Exception as e:
            log(f"openfigi failed: {e}")
            break
        for c, r in zip(chunk, res):
            data = r.get("data") or []
            cache[c] = data[0]["ticker"] if data else ""
    save_cache("figi.json", cache)
    return cache


def info_table(cik: int, acc: str) -> list[dict]:
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    idx = http_json(base + "index.json")
    names = [i["name"] for i in idx["directory"]["item"] if i["name"].lower().endswith(".xml")]
    names = [n for n in names if "primary_doc" not in n.lower()] or names
    rows = []
    for n in names:
        x = http(base + n).decode("utf-8", "replace")
        if "infoTable" not in x:
            continue
        root = ET.fromstring(x.encode("utf-8"))
        for el in root.iter():
            if isinstance(el.tag, str) and "}" in el.tag:
                el.tag = el.tag.split("}", 1)[1]
        for t in root.iter("infoTable"):
            rows.append({
                "name": (t.findtext("nameOfIssuer") or "").strip(),
                "cusip": (t.findtext("cusip") or "").strip().upper(),
                "value": float(t.findtext("value") or 0),
                "shares": float(t.findtext("./shrsOrPrnAmt/sshPrnamt") or 0),
                "put_call": (t.findtext("putCall") or "").strip(),
            })
        break
    return rows


def aggregate(rows: list[dict]) -> dict:
    out = {}
    for r in rows:
        if r["put_call"]:
            continue
        a = out.setdefault(r["cusip"], {"name": r["name"], "value": 0.0, "shares": 0.0})
        a["value"] += r["value"]
        a["shares"] += r["shares"]
    return out


def fetch_funds(sec: Sectors) -> dict:
    cache = cache_json("13f.json", {})  # accession -> aggregated holdings
    cards, ok, notes = [], 0, []
    for cik, label in FUNDS:
        try:
            sub = http_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
            r = sub["filings"]["recent"]
            f = [(r["filingDate"][i], r["accessionNumber"][i], r["reportDate"][i]) for i in range(len(r["form"])) if r["form"][i] == "13F-HR"]
            if len(f) < 1:
                notes.append(f"{label}: no 13F-HR found")
                continue
            books = []
            for filed, acc, period in f[:2]:
                if acc not in cache:
                    cache[acc] = aggregate(info_table(cik, acc))
                books.append((filed, acc, period, cache[acc]))
            filed, acc, period, cur = books[0]
            prev = books[1][3] if len(books) > 1 else {}
            total = sum(h["value"] for h in cur.values()) or 1
            top = sorted(cur.items(), key=lambda kv: kv[1]["value"], reverse=True)[:10]
            exits = sorted(((c, h) for c, h in prev.items() if c not in cur), key=lambda kv: kv[1]["value"], reverse=True)[:3]
            ptotal = sum(h["value"] for h in prev.values()) or 1
            tick = figi_tickers([c for c, _ in top] + [c for c, _ in exits])
            src = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm"
            q = dt.date.fromisoformat(period)
            qlabel = f"Q{(q.month - 1) // 3 + 1} {q.year}"
            stale = (dt.date.today() - dt.date.fromisoformat(filed)).days > 140
            for rank, (cusip, h) in enumerate(top, 1):
                t = tick.get(cusip) or ""
                w = h["value"] / total * 100
                p = prev.get(cusip)
                if not prev:
                    act, chg = "holding", "No prior 13F to compare."
                elif not p:
                    act, chg = "new position", "New since the prior 13F."
                else:
                    d = (h["shares"] - p["shares"]) / p["shares"] * 100 if p["shares"] else 0
                    act = "added" if d > 0.5 else "trimmed" if d < -0.5 else "unchanged"
                    chg = f"Shares {d:+.1f}% vs prior 13F." if act != "unchanged" else "Share count about unchanged vs prior 13F."
                sector = sec.for_ticker(t) if t else ""
                verb = {"new position": "NEW", "added": "ADD", "trimmed": "TRIM", "unchanged": "HOLD", "holding": "HOLD"}[act]
                sym = t or h["name"]
                cards.append(card(
                    id=f"13f-{acc}-{cusip}", entity=label, who=label, what=sym, action=act,
                    detail=f"#{rank} holding: {h['name']}. {w:.1f}% of the filed portfolio, {money(h['value'])}, {h['shares']:,.0f} shares. {chg}",
                    trade_date=period, public_date=filed, tickers=[sym], weights=[f"{w:.1f}%"], sector=sector,
                    why="Quarter-end long position from the manager's 13F-HR information table.",
                    confidence="Primary filing (SEC 13F-HR). Ticker mapped from CUSIP via OpenFIGI.",
                    caveats=("Old filing: this manager has not filed a newer 13F. " if stale else "") + "A 13F is a delayed snapshot of long U.S. positions, not trades. Options and shorts are not shown.",
                    source_url=src,
                    copy_line=f"{verb} {sym}, {w:.1f}% of portfolio, {label} 13F {qlabel} (filed {filed})",
                    csv={"fund": label, "ticker": t, "issuer": h["name"], "cusip": cusip, "weight_pct": round(w, 2),
                         "value_usd": round(h["value"]), "shares": round(h["shares"]), "change": act, "quarter_end": period,
                         "filed_date": filed, "sector": sector, "source_url": src},
                ))
            for cusip, h in exits:
                t = tick.get(cusip) or ""
                sym = t or h["name"]
                pw = h["value"] / ptotal * 100
                cards.append(card(
                    id=f"13f-{acc}-{cusip}-exit", entity=label, who=label, what=sym, action="sold out",
                    detail=f"{h['name']} was {pw:.1f}% of the prior 13F ({money(h['value'])}) and is absent from this one.",
                    trade_date=period, public_date=filed, tickers=[sym], weights=["0%"], sector=sec.for_ticker(t) if t else "",
                    why="Position present in the prior 13F and missing from the latest one.",
                    confidence="Primary filings (two SEC 13F-HRs compared).",
                    caveats="Could also be moved into options or below the reporting threshold.",
                    source_url=src,
                    copy_line=f"SOLD OUT {sym} (was {pw:.1f}%), {label} 13F {qlabel} (filed {filed})",
                    csv={"fund": label, "ticker": t, "issuer": h["name"], "cusip": cusip, "weight_pct": 0,
                         "value_usd": 0, "shares": 0, "change": "sold out", "quarter_end": period,
                         "filed_date": filed, "sector": "", "source_url": src},
                ))
            ok += 1
        except Exception as e:
            log(f"13F {label} failed: {e}")
            notes.append(f"{label}: fetch failed")
    save_cache("13f.json", cache)
    if not cards:
        raise RuntimeError("no 13F rows")
    log(f"funds: {ok}/{len(FUNDS)} managers, {len(cards)} rows")
    return {"cards": cards, "as_of": max(c["public_date"] for c in cards),
            "summary": f"Top 10 holdings and biggest exits for {ok} famous managers from their latest 13F.",
            "note": "; ".join(notes)}


# --------------------------------------------------------------- CRYPTO ----
def fetch_crypto(sec: Sectors) -> dict:
    cards = []
    today = dt.date.today().isoformat()
    for coin, sym in (("bitcoin", "BTC"), ("ethereum", "ETH")):
        d = http_json(f"https://api.coingecko.com/api/v3/companies/public_treasury/{coin}")
        src = f"https://www.coingecko.com/en/treasuries/{coin}"
        for rank, c in enumerate(d.get("companies", [])[:10], 1):
            held = float(c.get("total_holdings") or 0)
            val = float(c.get("total_current_value_usd") or 0)
            stock = (c.get("symbol") or "").strip()
            who = c.get("name") or "Unknown"
            us = stock.endswith(".US")
            tick = stock[:-3] if us else stock
            stock = tick if us else stock
            cards.append(card(
                id=f"cg-{sym}-{re.sub(r'[^a-z0-9]+', '-', who.lower())}", entity=f"Top {sym} treasuries", who=f"{who} ({stock or 'private'})",
                what=sym, action="treasury holding",
                detail=f"#{rank}: {held:,.0f} {sym}, about {money(val)} at today's price ({c.get('percentage_of_total_supply', 0)}% of supply). Country: {c.get('country') or 'n/a'}.",
                trade_date=today, public_date=today, tickers=[sym] + ([tick] if tick else []), sector="Crypto",
                why="Public companies that disclose holding crypto on their balance sheet.",
                confidence="Aggregator (CoinGecko) compiling company disclosures. Check the company's own filing.",
                caveats="Holdings change only when the company reports. Not a wallet balance.",
                source_url=src,
                copy_line=f"WATCH {sym} via {who} ({stock}): {held:,.0f} {sym} held (~{money(val)}), CoinGecko {today}",
                csv={"holder": who, "stock": stock, "coin": sym, "holdings": held, "value_usd": round(val),
                     "pct_supply": c.get("percentage_of_total_supply"), "as_of": today, "source_url": src},
            ))
    if not cards:
        raise RuntimeError("no treasury rows")
    log(f"crypto: {len(cards)} rows")
    return {"cards": cards, "as_of": today,
            "summary": "Top 10 public-company BTC and ETH treasuries. Whale wallets and ETF flows not connected.",
            "note": "Big-wallet and spot-ETF flow data are skipped: no free source with clear terms and stable labels."}


def social_section() -> dict:
    return {"cards": [card(
        id="social-coming-soon", sector="Coming soon", entity="Coming soon", who="Coming soon", what="—",
        action="not listed yet",
        detail="No account is listed until its calls can be checked against a public filing, a published portfolio, or a wallet it published itself.",
        trade_date="—", public_date="—", tickers=["—"],
        why="Follower counts and screenshots are not a track record.",
        confidence="Nothing to score yet.", caveats="SIFT will not invent or rank accounts.",
        source_url="https://www.sec.gov/edgar/search/", copy_line="", csv={})],
        "as_of": None, "summary": "Coming soon. Only accounts with a checkable public record will be listed.", "note": ""}


# ---------------------------------------------------------------- BUILD ----
META = {
    "congress": dict(title="Congress trades", source_name="U.S. House Clerk periodic transaction reports",
                     source_url="https://disclosures-clerk.house.gov/FinancialDisclosure", as_of_label="Trade date",
                     public_label="Filed",
                     blurb="Stock trades members of the House reported under the STOCK Act: member, ticker, buy or sell, amount range, trade date, and filing date. Each row links the original filing.",
                     lag="Members can file up to 45 days after a trade, so these are old news by the time they are public. Amounts are ranges."),
    "funds": dict(title="Famous funds (13F)", source_name="SEC EDGAR Form 13F-HR",
                  source_url="https://www.sec.gov/edgar/search/", as_of_label="Quarter-end", public_label="Filed",
                  blurb="Quarter-end long positions of well-known managers, with each position's weight in the filed portfolio and the change versus the prior quarter.",
                  lag="13F filings come out up to 45 days after quarter end, so the fund may have already changed its positions."),
    "insiders": dict(title="Insider buys", source_name="SEC EDGAR Form 4, transaction code P",
                     source_url="https://www.sec.gov/edgar/search/", as_of_label="Trade date", public_label="Filed",
                     blurb="Executives, directors, and 10% owners buying their own company's shares with their own money on the open market. Grants, option exercises, and 10b5-1 plan buys are excluded.",
                     lag="Form 4 is due within two business days of the trade."),
    "crypto": dict(title="Crypto treasuries", source_name="CoinGecko public treasury data (compiled from company disclosures)",
                   source_url="https://www.coingecko.com/en/treasuries/bitcoin", as_of_label="As of", public_label="Retrieved",
                   blurb="The public companies holding the most bitcoin and ether on their balance sheets. Data powered by CoinGecko.",
                   lag="Only as fresh as each company's last disclosure."),
    "social": dict(title="Verified social accounts", source_name="Primary filings, published portfolios, or self-published wallets only",
                   source_url="https://www.sec.gov/edgar/search/", as_of_label="Call date", public_label="Public",
                   blurb="A future top-10 list of accounts whose calls can be checked against a public record. Nothing is listed until it checks out.",
                   lag="A call counts only after the verifying record is public."),
}
FETCHERS = {"congress": fetch_congress, "insiders": fetch_insiders, "funds": fetch_funds, "crypto": fetch_crypto}


def build(only: set[str] | None) -> dict:
    prev = {}
    if DATA_PATH.is_file():
        try:
            old = json.loads(DATA_PATH.read_text())
            if not old.get("sample_only"):
                prev = {s["id"]: s for s in old.get("sections", [])}
        except Exception:
            pass
    now = dt.datetime.now(dt.timezone.utc).astimezone()
    sec = Sectors()
    sections, gaps = [], []
    for sid in SECTION_IDS:
        meta = META[sid]
        res, err = None, None
        if sid == "social":
            res = social_section()
        elif only is None or sid in only:
            t0 = time.time()
            try:
                res = FETCHERS[sid](sec)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                log(f"{sid} FAILED: {err}")
            log(f"{sid}: {time.time() - t0:.0f}s")
        if res is None:
            p = prev.get(sid)
            if p:
                p = dict(p)
                p["stale"] = True
                p["stale_note"] = "Could not refresh today; showing the last good data." if err else "Not refreshed in this run."
                sections.append(p)
                gaps.append(f"{meta['title']}: {p['stale_note']}")
            else:
                s = dict(id=sid, **meta, summary="Not available yet.", cards=[social_section()["cards"][0] | {"id": f"{sid}-unavailable", "entity": "Not available", "who": "Not available"}],
                         stale=True, stale_note="No data yet.", as_of=None, retrieved_at=None, note="")
                sections.append(s)
                gaps.append(f"{meta['title']}: no data yet.")
            continue
        s = dict(id=sid, **meta, summary=res["summary"], cards=res["cards"], stale=False, stale_note="",
                 as_of=res["as_of"], retrieved_at=now.isoformat(timespec="seconds"), note=res.get("note", ""))
        if res.get("note"):
            gaps.append(f"{meta['title']}: {res['note']}")
        sections.append(s)
    sec.save()
    gaps += ["Verified social accounts: coming soon, no account has a checkable public record yet.",
             "No backtest has been run on any of these streams yet."]
    return {
        "schema": 1, "preview": False, "phase": "2", "status": "Live public disclosures, refreshed daily",
        "sample_only": False,
        "disclaimer": "Not financial advice. Research and education only. Disclosures are delayed. Copying a holding is not the same as copying the result. Place any trade yourself at your own broker.",
        "copy_footer": NFA,
        "coverage": {
            "retrieved_at": now.isoformat(timespec="seconds"),
            "publication_label": "Every row links its original public source. Filing dates are shown on each row.",
            "freshness": f"Updated {now.strftime('%b %-d, %Y %-I:%M %p %Z')}",
            "gaps": gaps,
        },
        "sections": sections,
    }


def banned(node, where: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in BANNED_KEYS:
                fail(f"{where} contains '{key}', which this page must not publish")
            banned(value, where + "." + key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            banned(value, f"{where}[{i}]")


def fail(message: str) -> None:
    print("follow_money: " + message, file=sys.stderr)
    raise SystemExit(1)


def check(doc: dict) -> None:
    for key in ("schema", "preview", "phase", "status", "sample_only", "disclaimer", "coverage", "sections"):
        if key not in doc:
            fail("missing " + key)
    if doc["schema"] != 1:
        fail("schema must be 1")
    if [s["id"] for s in doc["sections"]] != list(SECTION_IDS):
        fail("expected sections " + ", ".join(SECTION_IDS))
    ids = set()
    for s in doc["sections"]:
        for k in SECTION_FIELDS:
            if k not in s:
                fail(s["id"] + " missing " + k)
        if not s["cards"]:
            fail(s["id"] + " has no cards")
        for c in s["cards"]:
            for k in CARD_FIELDS:
                if k not in c:
                    fail(f"{s['id']} card missing {k}")
            if c["id"] in ids:
                fail("duplicate card " + c["id"])
            ids.add(c["id"])
            if not c["sample"] and not str(c.get("source_url", "")).startswith("https://"):
                fail(c["id"] + " real row without an https source_url")
            if not isinstance(c["tickers"], list) or not c["tickers"]:
                fail(c["id"] + " tickers must be non-empty")
    banned(doc, "root")


def main(argv: list[str]) -> int:
    if "--check" in argv:
        doc = json.loads(DATA_PATH.read_text())
        check(doc)
        print(f"OK {DATA_PATH.name}: " + ", ".join(f"{s['id']}={len(s['cards'])}{' (stale)' if s.get('stale') else ''}" for s in doc["sections"]))
        return 0
    only = None
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    t0 = time.time()
    doc = build(only)
    check(doc)
    tmp = DATA_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(DATA_PATH)
    print(f"OK wrote {DATA_PATH} in {time.time() - t0:.0f}s: " + ", ".join(
        f"{s['id']}={len(s['cards'])}{' (stale)' if s.get('stale') else ''}" for s in doc["sections"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
