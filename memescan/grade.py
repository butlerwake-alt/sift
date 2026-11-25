"""Paper 24h grading from saved snapshots. No orders."""

from datetime import timedelta

import plan
import public_http
import store
from audit import iso, parse_time, snapshot, utc_now


def simulate(entry, points):
    """Walk snapshot prices. A print below a stop fills at that print."""
    if entry is None or entry <= 0:
        return None
    rows = []
    for point in points or []:
        price = point.get("price")
        elapsed = point.get("elapsed_s")
        if price is None or elapsed is None:
            continue
        price = float(price)
        elapsed = float(elapsed)
        if price <= 0 or elapsed < 0:
            continue
        rows.append((elapsed, price))
    if not rows:
        return None
    rows.sort(key=lambda item: item[0])
    prices = [price for _, price in rows]
    high = max([entry] + prices)
    low = min([entry] + prices)
    stop = entry * (1 - plan.STOP_PCT)
    target = entry * (1 + plan.TP1_PCT)
    units = (1.0 * (1 - plan.FEE)) / (entry * (1 + plan.SLIPPAGE))
    remaining = units
    proceeds = 0.0
    tp_done = False
    peak = entry
    exit_reason = None
    gap = False
    fill_mid = None

    def sell(amount, mid, reason, is_gap):
        nonlocal remaining, proceeds, exit_reason, gap, fill_mid
        take = min(remaining, amount)
        if take <= 0:
            return
        fill = mid * (1 - plan.SLIPPAGE)
        proceeds += take * fill * (1 - plan.FEE)
        remaining -= take
        exit_reason = reason
        fill_mid = mid
        if is_gap:
            gap = True

    for elapsed, price in rows:
        if remaining <= 1e-12:
            break
        if elapsed <= 0:
            continue
        if not tp_done and price >= target:
            sell(units * plan.TP1_FRACTION, target, "tp1", False)
            tp_done = True
            peak = max(peak, price)
        if remaining <= 1e-12:
            break
        if not tp_done and price <= stop:
            is_gap = price < stop
            sell(remaining, price if is_gap else stop, "stop_gap" if is_gap else "stop", is_gap)
            break
        if tp_done:
            peak = max(peak, price)
            trail = peak * (1 - plan.TRAIL)
            if price <= trail:
                is_gap = price < trail
                sell(remaining, price if is_gap else trail, "trail_gap" if is_gap else "trail", is_gap)
                break
        if (not tp_done) and elapsed >= plan.DEAD_AFTER_S and price < entry * (1 + plan.DEAD_BELOW_GAIN):
            sell(remaining, price, "dead", False)
            break
    if remaining > 1e-12:
        sell(remaining, rows[-1][1], "horizon", False)
    net = proceeds - 1.0
    return {
        "net_return": net,
        "high": high,
        "low": low,
        "gap": gap,
        "exit_reason": exit_reason,
        "fill_mid": fill_mid,
        "stop": stop,
        "doubled": high >= entry * 2.0,
        "fell_50": low <= entry * 0.5,
        "fell_90": low < entry * 0.1,
    }


def letter_grade(sim):
    if sim["fell_90"]:
        return "F"
    if sim["gap"]:
        return "D"
    if sim["exit_reason"] in {"stop", "trail"}:
        return "C"
    if sim["net_return"] >= 0.50:
        return "A"
    if sim["net_return"] >= 0:
        return "B"
    return "C"


def trap_call(verdict, sim):
    if verdict != "TRAP":
        return None
    missed = sim["doubled"] or sim["net_return"] >= 0.50
    avoided = sim["fell_50"] or sim["net_return"] < 0
    if missed and avoided:
        return "mixed"
    if missed:
        return "missed winner"
    if avoided:
        return "avoided loss"
    return None


def grade_path(entry, points, verdict):
    sim = simulate(entry, points)
    if sim is None:
        return None
    return {
        "grade": letter_grade(sim),
        "net_return": sim["net_return"],
        "exit_reason": sim["exit_reason"],
        "fill_mid": sim["fill_mid"],
        "stop": sim["stop"],
        "doubled": sim["doubled"],
        "fell_50": sim["fell_50"],
        "fell_90": sim["fell_90"],
        "low": sim["low"],
        "high": sim["high"],
        "audit_verdict": verdict,
        "audit_flagged": verdict in {"TRAP", "WARN"},
        "trap_call": trap_call(verdict, sim),
    }


def _median(values):
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def base_rates(graded):
    groups = {}
    for row in graded:
        version = row.get("rule_version") or "v1"
        feed = row.get("feed") or "—"
        verdict = row.get("verdict") or "UNKNOWN"
        groups.setdefault((verdict, version, feed), []).append(row)
    table = []
    keys = sorted(groups, key=lambda item: (item[1], item[2], item[0]))
    if not keys:
        keys = [(name, "v2", "—") for name in ("CLEAN", "WARN", "TRAP", "UNKNOWN")]
        groups = {key: [] for key in keys}
    for verdict, version, feed in keys:
        rows = groups.get((verdict, version, feed)) or []
        count = len(rows)
        nets = [row["net_return"] for row in rows if isinstance(row.get("net_return"), (int, float))]
        table.append({
            "verdict": verdict,
            "rule_version": version,
            "feed": feed,
            "n": count,
            "note": "too few to trust" if count < 30 else "",
            "pct_doubled": None if count == 0 else 100.0 * sum(1 for row in rows if row.get("doubled")) / count,
            "pct_fell_50": None if count == 0 else 100.0 * sum(1 for row in rows if row.get("fell_50")) / count,
            "median_net": _median(nets),
            "best": None if not nets else max(nets),
            "worst": None if not nets else min(nets),
        })
    return table


def points_for(card, snaps, now):
    opened = parse_time(card.get("t0"))
    entry = card.get("price_t0")
    if opened is None or entry is None:
        return None
    if now < opened + timedelta(seconds=plan.HORIZON_S):
        return None
    chosen = []
    for snap in snaps:
        if snap.get("mint") != card.get("mint"):
            continue
        moment = parse_time(snap.get("t"))
        price = snap.get("price_usd")
        if moment is None or price is None:
            continue
        if moment < opened or moment > opened + timedelta(seconds=plan.HORIZON_S):
            continue
        chosen.append({
            "elapsed_s": (moment - opened).total_seconds(),
            "price": price,
            "source": snap.get("source"),
            "fetched_at": snap.get("fetched_at"),
        })
    if not chosen:
        return None
    if max(point["elapsed_s"] for point in chosen) < plan.SNAPSHOT_READY_S:
        return None
    return chosen


def main():
    import board

    now = utc_now()
    graded_keys = {(row.get("mint"), row.get("t0")) for row in store.read_jsonl("graded.jsonl")}
    snaps = store.read_jsonl("snapshots.jsonl")
    wrote = 0
    for card in store.read_jsonl("cards.jsonl"):
        key = (card.get("mint"), card.get("t0"))
        if key in graded_keys:
            continue
        points = points_for(card, snaps, now)
        if points is None:
            continue
        result = grade_path(card.get("price_t0"), points, card.get("verdict"))
        if result is None:
            continue
        sources = sorted({point.get("source") for point in points if point.get("source")})
        record = {
            "label": card.get("label") or plan.LABEL,
            "rule_version": card.get("rule_version") or "v1",
            "feed": card.get("feed") or "—",
            "mint": card.get("mint"),
            "symbol": card.get("symbol"),
            "name": card.get("name"),
            "t0": card.get("t0"),
            "price_t0": card.get("price_t0"),
            "price_source": card.get("price_source"),
            "verdict": card.get("verdict"),
            "score": card.get("score"),
            "graded_at": iso(now),
            "snapshot_count": len(points),
            "snapshot_sources": sources,
            "plan": card.get("plan") or plan.plan_dict(),
        }
        record.update(result)
        store.append_jsonl("graded.jsonl", record)
        graded_keys.add(key)
        wrote += 1
        print("graded %s %s net %.4f" % (card.get("symbol"), result["grade"], result["net_return"]))
    if wrote == 0:
        print("memescan grade: no card has a full 24h snapshot path yet.")
    board.write_board()
    return 0


def refresh_prices(mints):
    """One public DexScreener read for coins that still have an open paper card."""
    if not mints:
        return
    from audit import DEX_TOKEN_URL, fetch_pairs

    try:
        pairs = fetch_pairs(list(mints))
    except public_http.SourceUnavailable as err:
        print("memescan snapshots: DexScreener down (%s). Not inventing prices." % err)
        return
    moment = utc_now()
    for mint, pair in pairs.items():
        price = pair.get("priceUsd")
        try:
            price = float(price)
        except (TypeError, ValueError):
            continue
        snapshot(mint, price, DEX_TOKEN_URL + mint, moment)


if __name__ == "__main__":
    raise SystemExit(main())
