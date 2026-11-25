"""Build the page payload from saved paper records. Does not fetch prices."""

from datetime import timedelta

import plan
import store
from audit import parse_time, utc_now

RULES = store.ROOT / "AUDIT_RULES.md"
MANIFEST = store.ROOT / "MANIFEST.json"


def _rules_sha():
    import json
    if not MANIFEST.exists():
        return None
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8")).get("sha256")
    except json.JSONDecodeError:
        return None


def latest_audits():
    rows = store.read_jsonl("audits.jsonl")
    newest = {}
    for row in rows:
        mint = row.get("mint")
        if not mint:
            continue
        previous = newest.get(mint)
        if previous is None or str(row.get("audited_at") or "") >= str(previous.get("audited_at") or ""):
            newest[mint] = row
    ordered = sorted(newest.values(), key=lambda row: str(row.get("audited_at") or ""), reverse=True)
    return ordered[: plan.CANDIDATE_CAP]


def recent_graded(now):
    cutoff = now - timedelta(days=7)
    rows = []
    for row in store.read_jsonl("graded.jsonl"):
        moment = parse_time(row.get("graded_at")) or parse_time(row.get("t0"))
        if moment is not None and moment >= cutoff:
            rows.append(row)
    rows.sort(key=lambda row: str(row.get("graded_at") or ""), reverse=True)
    return rows


def write_board():
    from grade import base_rates

    now = utc_now()
    payload = {
        "label": plan.LABEL,
        "banner": plan.BANNER,
        "why": plan.WHY,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rules_sha256": _rules_sha(),
        "audits": latest_audits(),
        "graded": recent_graded(now),
        "base_rates": base_rates(store.read_jsonl("graded.jsonl")),
    }
    store.write_json("board.json", payload)
    return payload
