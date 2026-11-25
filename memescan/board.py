"""Build the page payload from saved paper records. Does not fetch prices."""

from datetime import timedelta

import plan
import store
from audit import parse_time, utc_now

MANIFEST = store.ROOT / "MANIFEST.json"


def _manifest():
    import json
    if not MANIFEST.exists():
        return {}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def latest_audits():
    rows = store.read_jsonl("audits.jsonl")
    newest = {}
    for row in rows:
        mint = row.get("mint")
        if not mint:
            continue
        version = row.get("rule_version") or "v1"
        key = (mint, version)
        previous = newest.get(key)
        if previous is None or str(row.get("audited_at") or "") >= str(previous.get("audited_at") or ""):
            newest[key] = row
    return sorted(newest.values(), key=lambda row: (row.get("rule_version") or "v1", str(row.get("audited_at") or "")), reverse=True)


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
    manifest = _manifest()
    payload = {
        "label": plan.LABEL_V2,
        "label_v1": plan.LABEL,
        "banner": plan.BANNER,
        "why": plan.WHY,
        "why_v2": plan.WHY_V2_NOTE,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rules_sha256": manifest.get("sha256"),
        "rules_sha256_v2": (manifest.get("v2") or {}).get("sha256"),
        "audits": latest_audits(),
        "graded": recent_graded(now),
        "base_rates": base_rates(store.read_jsonl("graded.jsonl")),
    }
    store.write_json("board.json", payload)
    return payload
