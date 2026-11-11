#!/usr/bin/env python3
"""Regenerate SIFT data.js from the daily paper-test records on the box.

Descriptive text (rules, hypothesis, backtest, risk...) comes from template.json,
which is the text of the site's original data.js. Numbers come only from the
paper-test state/ledger files. Dated marks are appended to history.json and are
never rewritten. If a strategy's records can't be read, its previous values are
kept and it is marked stale. Paper only; reads files, never trades.
"""
import csv, glob, json, math, os, re, sys, datetime as dt
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
W = "/workspace"
NY = ZoneInfo("America/New_York")
TODAY = dt.datetime.now(NY).date()
CAP = 10000.0
STALE_DAYS = 4

def money(v): return "${:,.2f}".format(v)
def pct(v):
    s = "+" if v > 0.00499 else ("−" if v < -0.00499 else "")
    return s + "{:.2f}%".format(abs(v))
def ret(v, base=CAP): return (v / base - 1) * 100
def d10(s): return str(s)[:10]
def label(iso):
    d = dt.date.fromisoformat(iso); return d.strftime("%b ") + str(d.day)
def rows(path):
    with open(path, newline="") as f: return list(csv.DictReader(f))

# ---------- readers: each returns dict(series=..., fields=...) ----------
def equity_series(path, eq="equity", bench=None, bench_is_price=False):
    rs = rows(path)
    acct = [{"date": d10(r["date"]), "equity": round(float(r[eq]), 2)} for r in rs]
    b = None
    if bench:
        p0 = float(rs[0][bench])
        b = [{"date": d10(r["date"]),
              "equity": round(CAP * float(r[bench]) / p0 if bench_is_price else float(r[bench]), 2)} for r in rs]
    return acct, b

def ledger_counts(path, exit_event="EXIT"):
    rs = rows(path)
    ents = sum(1 for r in rs if r["event"] == "ENTRY")
    ex = [float(r["pnl"]) for r in rs if r["event"] == exit_event]
    return ents, ex

def closed_text(ex):
    if not ex: return "0 closed"
    w = sum(1 for p in ex if p > 0)
    return "{} closed ({} won, {} lost, {} total, win rate {:.0f}%)".format(
        len(ex), w, len(ex) - w, ("+" if sum(ex) >= 0 else "−") + money(abs(sum(ex))), 100 * w / len(ex))

def read_meanrev(folder, bench_name):
    acct, b = equity_series(f"{W}/{folder}/equity.csv", bench="btc_value")
    last = rows(f"{W}/{folder}/equity.csv")[-1]
    ents, ex = ledger_counts(f"{W}/{folder}/trades.csv")
    lat = acct[-1]["equity"]; bl = b[-1]["equity"]
    return dict(acct=acct, bench=b, latest=lat, change=pct(ret(lat)), asOf=acct[-1]["date"],
        forward="{} ({}). {} positions open, {}. {} {} ({}).".format(
            money(lat), pct(ret(lat)), int(float(last["open_positions"])), closed_text(ex), bench_name, money(bl), pct(ret(bl))))

def read_zscore(): return read_meanrev("zscore_crypto", "BTC buy-and-hold")
def read_bollinger(): return read_meanrev("bollinger_crypto", "BTC buy-and-hold")

def read_dipbuy():
    acct, b = equity_series(f"{W}/dipbuy_sp500/equity.csv", bench="spy_value")
    last = rows(f"{W}/dipbuy_sp500/equity.csv")[-1]
    ents, ex = ledger_counts(f"{W}/dipbuy_sp500/trades.csv")
    lat = acct[-1]["equity"]; bl = b[-1]["equity"]
    return dict(acct=acct, bench=b, latest=lat, change=pct(ret(lat)), asOf=acct[-1]["date"],
        forward="{} ({}) against SPY {} ({}). {} positions open, {}.".format(
            money(lat), pct(ret(lat)), money(bl), pct(ret(bl)), int(float(last["open_positions"])), closed_text(ex)))

def read_scalein():
    acct, b = equity_series(f"{W}/scalein_basket/equity.csv", bench="btc_hold")
    last = rows(f"{W}/scalein_basket/equity.csv")[-1]
    lat = acct[-1]["equity"]; cash = float(last["cash"])
    held = [k.replace("hold_", "").replace("-USD", "") for k, v in last.items() if k.startswith("hold_") and float(v or 0) > 0]
    cash_pct = 100 * cash / lat if lat else 0
    ch = "100% cash" if cash_pct > 99.95 else "{:.0f}% cash".format(cash_pct)
    return dict(acct=acct, bench=b, latest=lat, change=ch if abs(ret(lat)) < 0.005 else pct(ret(lat)) + " · " + ch, asOf=acct[-1]["date"],
        forward="{} ({}), {} through the {} close. {}Max drawdown {:.2f}%. BTC buy-and-hold {} ({}). Equal-weight basket hold {}. The forward test has not proven anything yet.".format(
            money(lat), pct(ret(lat)), ch, label(acct[-1]["date"]),
            ("Holding " + ", ".join(held) + ". ") if held else "",
            float(last["maxdd_pct"]), money(b[-1]["equity"]), pct(ret(b[-1]["equity"])), money(float(last["basket_hold"]))))

def social(tag, bench_name):
    acct, b = equity_series(f"{W}/social_paper/runs/{tag}/equity.csv", bench="benchmark", bench_is_price=True)
    st = json.load(open(f"{W}/social_paper/state/{tag}.json"))
    tp = f"{W}/social_paper/runs/{tag}/trades.csv"
    tr = rows(tp) if os.path.exists(tp) else []
    sells = sum(1 for r in tr if r["side"] == "SELL")
    lat = acct[-1]["equity"]
    held = [k for k, v in (st.get("holdings") or {}).items() if v]
    return acct, b, lat, held, len(tr), sells

def read_social(tag, bench_name, extra=""):
    acct, b, lat, held, ntr, sells = social(tag, bench_name)
    pos = ("holds " + ", ".join(held)) if held else "in cash"
    ch = pct(ret(lat)) if held or abs(ret(lat)) >= 0.005 else ("flat" if abs(ret(lat)) < 0.005 else "in cash")
    if not held and abs(ret(lat)) >= 0.005: ch = "in cash · " + pct(ret(lat))
    return dict(acct=acct, bench=b, latest=lat, change=ch, asOf=acct[-1]["date"],
        forward="{} ({}), {} as of the {} close. {} fills logged, {} sells. {} {} ({}).{}".format(
            money(lat), pct(ret(lat)), pos, label(acct[-1]["date"]), ntr, sells, bench_name,
            money(b[-1]["equity"]), pct(ret(b[-1]["equity"])), extra))

def read_ema(): return read_social("ema_1d", "BTC buy-and-hold")
def read_botwars(): return read_social("botwars_1d", "BTC buy-and-hold")
def read_halving(): return read_social("halving_500", "BTC buy-and-hold", " Next frozen buy date: Dec 14, 2026.")
def read_nasdaq(): return read_social("nasdaq_top5", "QQQ buy-and-hold")

def read_emavwap():
    B = f"{W}/ema_vwap_paper"
    st = json.load(open(f"{B}/state/forward.json"))
    fills = [json.loads(l) for l in open(f"{B}/state/fills.jsonl")] if os.path.exists(f"{B}/state/fills.jsonl") else []
    P = st["processed"]
    if not P: raise RuntimeError("no sessions processed yet")
    out = {}
    for m in ("primary", "variant"):
        eq = CAP; pts = [{"date": st["start"], "equity": CAP, "session": "open"}]
        pn = []
        for d in P:
            day = [f["event"][4] for f in fills if f["mode"] == m and f["session"] == d and f["event"][1] == "SELL"]
            pn += day; eq += sum(day)
            pts.append({"date": d, "equity": round(eq, 2), "session": "close"})
        out[m] = (pts, pn, round(sum(st["acct"][m].values()), 2))
    # 50/50 buy-and-hold from the first session's open, same math as report.py
    first = {}; closes = {}
    for s in ("SPY", "QQQ"):
        f = sorted(glob.glob(f"{B}/raw/{s}_5m_*.csv"))[-1]
        for r in rows(f):
            t = dt.datetime.fromisoformat(r["Datetime"]).astimezone(NY); day = t.date().isoformat()
            if day < P[0] or day > P[-1]: continue
            first.setdefault(s, float(r["Open"])); closes.setdefault(s, {})[day] = float(r["Close"])
    bpts = [{"date": st["start"], "equity": CAP, "session": "open"}]
    for d in P:
        if all(d in closes.get(s, {}) for s in ("SPY", "QQQ")):
            v = CAP * (1 + sum(closes[s][d] / first[s] - 1 for s in ("SPY", "QQQ")) / 2)
            bpts.append({"date": d, "equity": round(v, 2), "session": "close"})
    pp, ppn, peq = out["primary"]; vp, vpn, veq = out["variant"]
    def tstats(pn):
        if not pn: return "0 trades"
        return "{} trades, win rate {:.0f}%".format(len(pn), 100 * sum(1 for x in pn if x > 0) / len(pn))
    bl = bpts[-1]["equity"]
    return dict(acct=pp, extra=vp, bench=bpts, latest=peq, change="primary " + pct(ret(peq)) + " · variant " + pct(ret(veq)),
        asOf=P[-1], sessions=len(P),
        forward="{} session{} through {}: primary {} ({}, {}); variant {} ({}, {}); 50/50 SPY/QQQ buy-and-hold {} ({}). Each version is its own $10,000 account split across SPY and QQQ.".format(
            len(P), "" if len(P) == 1 else "s", label(P[-1]), money(peq), pct(ret(peq)), tstats(ppn),
            money(veq), pct(ret(veq)), tstats(vpn), money(bl), pct(ret(bl))))


# ---------- regime_paper (strategies 11-17, forward paper from the Nov 10, 2026 close) ----------
RP = f"{W}/regime_paper"
def read_regime_paper(tag, bench_name):
    acct, b = equity_series(f"{RP}/runs/{tag}/equity.csv", bench="benchmark", bench_is_price=True)
    last = rows(f"{RP}/runs/{tag}/equity.csv")[-1]
    st = json.load(open(f"{RP}/state/{tag}.json"))
    tr = rows(f"{RP}/runs/{tag}/trades.csv")
    sells = sum(1 for r in tr if r["side"] == "SELL")
    lat = acct[-1]["equity"]
    held = sorted(a.replace("-USD", "") for a, u in (st.get("holdings") or {}).items() if u)
    queued = sorted(a for a, w in (st.get("pending_target") or {}).items() if w)
    pos = ("holds " + ", ".join(held)) if held else "100% cash"
    if not tr and len(acct) == 1:
        ch = "forward start"
        q = ("First buys queued for the next close: " + ", ".join(queued) + ".") if queued else "No buy signal at the start; waiting in cash."
        fwd = "{} paper, opened at the {} close. {} Regime at the start: {}.".format(money(lat), label(acct[-1]["date"]), q, last.get("regime") or "n/a")
    else:
        ch = pct(ret(lat)) if held or abs(ret(lat)) >= 0.005 else "100% cash"
        fwd = "{} ({}), {} as of the {} close. {} fills logged, {} sells. {} {} ({}). Regime that day: {}.".format(
            money(lat), pct(ret(lat)), pos, label(acct[-1]["date"]), len(tr), sells, bench_name,
            money(b[-1]["equity"]), pct(ret(b[-1]["equity"])), last.get("regime") or "n/a")
    return dict(acct=acct, bench=b, latest=lat, change=ch, asOf=acct[-1]["date"], forward=fwd)

def read_regime():
    try: return json.load(open(f"{RP}/state/regime.json"))
    except Exception: return None

RP_TAGS = {11: ("s11_breakout", "SPY buy-and-hold"), 12: ("s12_squeeze", "SPY buy-and-hold"), 13: ("s13_btc200", "BTC buy-and-hold"),
           14: ("s14_leader_pb", "SPY buy-and-hold"), 15: ("s15_crypto_brk", "BTC buy-and-hold"), 16: ("s16_crypto_mom3", "BTC buy-and-hold"),
           17: ("s17_rotator", "SPY buy-and-hold")}

READERS = {1: read_scalein, 2: read_zscore, 3: read_bollinger, 4: read_ema, 5: read_botwars,
           6: read_halving, 8: read_dipbuy, 9: read_nasdaq, 10: read_emavwap}  # 7 = SEASONS, planned
for _n, (_tag, _bn) in RP_TAGS.items():
    READERS[_n] = (lambda t=_tag, b=_bn: read_regime_paper(t, b))

# ---------- history (append-only) ----------
def key(p): return p["date"] + "|" + p.get("session", "")
def merge(hist, series):
    have = {key(p) for p in hist}
    for p in series:
        if key(p) not in have: hist.append(dict(p)); have.add(key(p))
    hist.sort(key=lambda p: (p["date"], p.get("session") == "close"))
    return hist

def main():
    tpl = json.load(open(f"{HERE}/template.json"))
    hp = f"{HERE}/history.json"
    H = json.load(open(hp)) if os.path.exists(hp) else {"note": "Append-only daily marks from the paper-test records. Existing marks are never rewritten.", "series": {}, "last": {}}
    report = {}
    strategies = []
    for s in tpl["strategies"]:
        s = json.loads(json.dumps(s)); n = s["n"]; sid = str(n)
        if s.get("planned"):
            strategies.append(s); report[n] = "planned"; continue
        try:
            r = READERS[n]()
            ser = H["series"].setdefault(sid, {})
            s["points"] = merge(ser.setdefault("acct", []), r["acct"])
            if r.get("extra") is not None: s["extra"]["points"] = merge(ser.setdefault("extra", []), r["extra"])
            if r.get("bench") is not None:
                bp = merge(ser.setdefault("bench", []), r["bench"])
                bname = (s.get("benchmark") or {}).get("name") or ("QQQ buy-and-hold" if n == 9 else "BTC buy-and-hold")
                if n == 10: bname = "50/50 SPY/QQQ buy-and-hold"
                if n in RP_TAGS: bname = RP_TAGS[n][1]
                bcolor = (s.get("benchmark") or {}).get("color") or ("#f0c53a" if s["color"] != "#f0c53a" else "#3c7dff")
                s["benchmark"] = {"name": bname, "color": bcolor, "points": bp}
            s["start"] = s["points"][0]["date"]
            s["latest"] = r["latest"]; s["change"] = r["change"]; s["forward"] = r["forward"]
            s["asOf"] = r["asOf"]
            age = (TODAY - dt.date.fromisoformat(r["asOf"])).days
            s["asOfLabel"] = "mark of " + label(r["asOf"]) + (" · stale ({} days old)".format(age) if age > STALE_DAYS else "")
            s["stale"] = age > STALE_DAYS
            if n == 10:
                s.pop("scale", None); s.pop("sleeveNote", None)
                s["lineName"] = "Primary account"
                s["tag"] = "Day {}".format(r["sessions"]) if r["sessions"] < 20 else "Forward paper"
                s["asOfLabel"] = "session {} · {}".format(r["sessions"], label(r["asOf"]))
            H["last"][sid] = s
            report[n] = "live" + (" (stale)" if s["stale"] else "")
        except Exception as e:
            prev = H["last"].get(sid)
            if prev:
                s = json.loads(json.dumps(prev))
                s["points"] = H["series"].get(sid, {}).get("acct", s["points"])
            if not s.get("points"):
                s["points"] = [{"date": s.get("start") or TODAY.isoformat(), "equity": CAP}]
            if s.get("latest") is None: s["latest"] = s["points"][-1]["equity"]
            s["stale"] = True
            s["asOfLabel"] = (s.get("asOfLabel") or "") + " · stale: records unreadable"
            s["tag"] = "Stale"
            report[n] = "STALE ({}: {})".format(type(e).__name__, e)
        strategies.append(s)

    # 'why' (the original backtest that led to the pick) is REQUIRED for every strategy and always comes from template.json,
    # so it survives regeneration and the stale-record fallback. See README.md.
    why = {x["n"]: x.get("why") for x in tpl["strategies"]}
    for s in strategies:
        s["why"] = why.get(s["n"])
        if not (isinstance(s["why"], dict) and s["why"].get("text")):
            raise SystemExit("template.json strategy {} is missing the required 'why' field".format(s["n"]))

    vals = []
    for s in strategies:
        for k in ("points",): vals += [p["equity"] for p in s.get(k, [])]
        if s.get("extra"): vals += [p["equity"] for p in s["extra"]["points"]]
        if s.get("benchmark") and s["benchmark"].get("points"): vals += [p["equity"] for p in s["benchmark"]["points"]]
    lo = min(vals + [CAP]); hi = max(vals + [CAP])
    mmin = int(math.floor((lo - 150) / 200.0) * 200); mmax = int(math.ceil((hi + 150) / 200.0) * 200)

    asof = max(s["asOf"] for s in strategies if s.get("asOf"))
    d = dt.date.fromisoformat(asof); asof_txt = d.strftime("%B ") + str(d.day) + d.strftime(", %Y")
    built = dt.datetime.now(NY).strftime("%Y-%m-%d %H:%M %Z")
    SIFT = {"asOf": asof_txt, "builtAt": built,
            "source": "Daily paper-test records (state and ledger files of each paper engine)",
            "capital": CAP, "moneyMin": mmin, "moneyMax": mmax, "strategies": strategies}
    reg = read_regime()
    if reg: SIFT["regime"] = reg
    js = ("/* Generated by build_data.py at {} from the daily paper-test records.\n"
          "   Do not edit by hand. Marks accumulate in history.json and are never rewritten. Paper only. */\n"
          "const SIFT = {};\n").format(built, json.dumps(SIFT, indent=1, ensure_ascii=False))
    tmp = f"{HERE}/data.js.tmp"; open(tmp, "w").write(js); os.replace(tmp, f"{HERE}/data.js")
    json.dump(H, open(f"{HERE}/history.json.tmp", "w"), indent=1); os.replace(f"{HERE}/history.json.tmp", hp)

    # keep the page header/footer dates in step with the data
    ip = f"{HERE}/index.html"; html = open(ip).read()
    html = re.sub(r'(<p class="eyebrow">Paper research · )[^<]*(</p>)', r"\g<1>" + asof_txt + r"\g<2>", html)
    html = re.sub(r"Source: [^<]*</footer>", "Source: daily paper-test records, latest mark " + asof_txt + ", built " + built + ".</footer>", html)
    open(ip, "w").write(html)
    for n in sorted(report): print("{:>2} {}".format(n, report[n]))
    print("asOf", asof_txt, "range", mmin, mmax)

if __name__ == "__main__":
    main()
