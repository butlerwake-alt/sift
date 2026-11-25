"""JSONL helpers for memescan/data. Paper records only."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def path(name):
    DATA.mkdir(parents=True, exist_ok=True)
    return DATA / name


def append_jsonl(name, obj):
    target = path(name)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")


def read_jsonl(name):
    target = DATA / name
    if not target.exists():
        return []
    rows = []
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def write_json(name, obj):
    target = path(name)
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    target.write_text(text + "\n", encoding="utf-8", newline="\n")


def read_json(name):
    target = DATA / name
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))
