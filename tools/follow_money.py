#!/usr/bin/env python3
"""Offline stub for the Follow the Money preview.

Validates data/follow_money.json and prints the public-source inventory.
Does not open a socket. Does not fetch House, Senate, EDGAR, issuer, or
chain data. See docs/follow_the_money/DESIGN.md.

Usage:
  python3 tools/follow_money.py
  python3 tools/follow_money.py --check
  python3 tools/follow_money.py --fetch   # refused; still offline
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "follow_money.json"

SECTION_IDS = ("congress", "funds", "insiders", "crypto", "social")
CARD_FIELDS = (
    "id",
    "sample",
    "entity",
    "who",
    "what",
    "action",
    "detail",
    "trade_date",
    "public_date",
    "why",
    "confidence",
    "caveats",
    "tickers",
    "weights",
)
SECTION_FIELDS = (
    "id",
    "title",
    "summary",
    "blurb",
    "source_name",
    "source_url",
    "as_of_label",
    "public_label",
    "lag",
    "cards",
)
BANNED_KEYS = {
    "cagr",
    "return_pct",
    "sharpe",
    "backtest",
    "win_rate",
    "total_return",
    "performance",
}

# Documented sources only. Nothing here is requested at runtime.
SOURCES = (
    {
        "id": "congress",
        "name": "House Clerk periodic transaction reports and Senate eFD",
        "urls": (
            "https://disclosures-clerk.house.gov/FinancialDisclosure",
            "https://efdsearch.senate.gov/",
        ),
        "terms": "House pages are public HTML/PDF with no documented bulk API. Senate eFD shows a usage agreement and is not a bulk API.",
        "rate": "No published quota. Design cap until the owner approves a client: under 1 request/second per host. Not called by this stub.",
        "lag": "PTR due within 30 days of notice and no later than 45 days after the transaction.",
    },
    {
        "id": "funds",
        "name": "SEC EDGAR Form 13F-HR",
        "urls": (
            "https://www.sec.gov/os/accessing-edgar-data",
            "https://www.sec.gov/edgar/search/",
        ),
        "terms": "EDGAR fair access. A future client must send a descriptive User-Agent.",
        "rate": "SEC-published cap: 10 requests/second. Not called by this stub.",
        "lag": "Due within 45 days after quarter end. Snapshot of long positions, not a trade blotter.",
    },
    {
        "id": "insiders",
        "name": "SEC EDGAR Form 4, transaction code P only",
        "urls": ("https://www.sec.gov/edgar/search/",),
        "terms": "Same EDGAR fair-access policy. Grants (A), exercises (M), and 10b5-1 plan rows stay out of the open-market list.",
        "rate": "SEC-published cap: 10 requests/second. Not called by this stub.",
        "lag": "Form 4 due within two business days, plus a processing delay before use.",
    },
    {
        "id": "crypto",
        "name": "Issuer holdings pages, company filings, already-labeled wallets",
        "urls": ("https://www.sec.gov/edgar/search/",),
        "terms": "Issuer sites have their own terms. Unlabeled addresses are not assigned to a person.",
        "rate": "Per-publisher. No provider is selected and no key is stored. Not called by this stub.",
        "lag": "As fresh as the cited page, plus processing time.",
    },
    {
        "id": "social",
        "name": "Accounts checkable against a filing, a published portfolio, or a self-published wallet",
        "urls": ("https://www.sec.gov/edgar/search/",),
        "terms": "Follower counts and screenshots are not verification. The top-10 list is empty until a source checks out.",
        "rate": "No social API is called.",
        "lag": "Usable only after the verifying source is public, plus processing time.",
    },
)


def fail(message: str) -> None:
    print("follow_money: " + message, file=sys.stderr)
    raise SystemExit(1)


def banned(node, where: str) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in BANNED_KEYS:
                fail(f"{where} contains '{key}', which this preview must not publish")
            banned(value, where + "." + key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            banned(value, f"{where}[{i}]")


def check(doc: dict) -> None:
    if not isinstance(doc, dict):
        fail("root must be an object")
    for key in ("schema", "preview", "phase", "status", "sample_only", "disclaimer", "coverage", "sections"):
        if key not in doc:
            fail("missing " + key)
    if doc["schema"] != 1:
        fail("schema must be 1")
    if doc["preview"] is not True:
        fail("preview must stay true until a live feed is approved")
    if "coming soon" not in str(doc["status"]).lower() and "preview" not in str(doc["status"]).lower():
        fail("status must say this is a preview")
    coverage = doc["coverage"]
    if not isinstance(coverage, dict) or not isinstance(coverage.get("gaps"), list) or not coverage["gaps"]:
        fail("coverage.gaps must list what is not connected")
    sections = doc["sections"]
    if not isinstance(sections, list) or len(sections) != len(SECTION_IDS):
        fail("expected the five streams: " + ", ".join(SECTION_IDS))
    seen = []
    ids = []
    for section in sections:
        if not isinstance(section, dict):
            fail("section must be an object")
        for key in SECTION_FIELDS:
            if key not in section:
                fail(section.get("id", "?") + " missing " + key)
        if section["id"] not in SECTION_IDS:
            fail("unknown section " + str(section["id"]))
        if section["id"] in seen:
            fail("duplicate section " + section["id"])
        seen.append(section["id"])
        if not str(section["source_url"]).startswith("https://"):
            fail(section["id"] + " source_url must be https")
        if not str(section["lag"]).strip():
            fail(section["id"] + " lag is empty")
        cards = section["cards"]
        if not isinstance(cards, list) or not cards:
            fail(section["id"] + " needs at least one sample card")
        for card in cards:
            if not isinstance(card, dict):
                fail("card must be an object")
            for key in CARD_FIELDS:
                if key not in card:
                    fail(section["id"] + " card missing " + key)
            if doc["sample_only"] and card["sample"] is not True:
                fail(card["id"] + " must be marked sample while sample_only is true")
            if not isinstance(card["tickers"], list) or not card["tickers"]:
                fail(card["id"] + " tickers must be a non-empty list")
            if not isinstance(card["weights"], list):
                fail(card["id"] + " weights must be a list")
            if card["id"] in ids:
                fail("duplicate card " + card["id"])
            ids.append(card["id"])
    banned(doc, "root")


def print_inventory() -> None:
    print("Follow the Money source inventory (not fetched)")
    print("Design: docs/follow_the_money/DESIGN.md")
    print()
    for source in SOURCES:
        print(source["id"] + " — " + source["name"])
        for url in source["urls"]:
            print("  " + url)
        print("  terms: " + source["terms"])
        print("  rate:  " + source["rate"])
        print("  lag:   " + source["lag"])
        print()


def main(argv: list[str]) -> int:
    if "--fetch" in argv:
        print(
            "Network fetch is disabled. This stub does not contact House, Senate, SEC, issuers, or chain explorers.",
            file=sys.stderr,
        )
        return 2
    unknown = [arg for arg in argv if arg not in ("--check",)]
    if unknown:
        print("Unknown arguments: " + " ".join(unknown), file=sys.stderr)
        return 2
    if not DATA_PATH.is_file():
        fail("missing " + str(DATA_PATH))
    with DATA_PATH.open(encoding="utf-8") as handle:
        doc = json.load(handle)
    check(doc)
    print_inventory()
    print(f"OK {DATA_PATH.name}: schema {doc['schema']}, {len(doc['sections'])} sections, sample_only={doc['sample_only']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
