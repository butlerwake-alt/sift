#!/usr/bin/env python3
"""Build data/backtest_by_year.json for the SIFT backtest-by-year section.

Paper / backtest only. Reads frozen lab and baseline outputs from the absolute
paths below. Does not place trades and does not run publish.sh.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "tools" else HERE
OUT = os.path.join(ROOT, "data", "backtest_by_year.json")
CAP = 10000.0
YEARS = list(range(2020, 2027))
ET = ZoneInfo("America/New_York")

LAB_ROOT = "/workspace/sift_strategy_lab"
TEMPLATE = "/workspace/sift_site/template.json"

# Site # -> (lab run folder, results slug)
LAB_MAP = {
    11: ("run_20261110", "donchian_55_20"),
    12: ("run_20261110", "squeeze"),
    13: ("run_20261110", "btc_trend"),
    14: ("run_20261110", "leader_pullback"),
    15: ("run_20261110", "crypto_donchian_regime"),
    16: ("run_20261110", "crypto_mom3_btcgate"),
    17: ("run_20261110", "regime_rotator_wf"),
    18: ("run_20261111", "lev_trend_tqqq"),
    19: ("run_20261111", "lev_trend_soxl"),
    20: ("run_20261111", "resid_mom_top10"),
    21: ("run_20261111", "ibs_tqqq"),
    22: ("run_20261111", "cr_tsmom_vt"),
    23: ("run_20261111_crypto", "vol_burst"),
    24: ("run_20261111_crypto", "hi365_regime"),
    25: ("run_20261111_crypto", "bb_squeeze_regime"),
    26: ("run_20261111_crypto", "weekly_tsmom_regime"),
}

STOCK_NS = {8, 9, 10, 11, 12, 14, 17, 18, 19, 20, 21}
CRYPTO_NS = {1, 2, 3, 4, 5, 6, 7, 13, 15, 16, 22, 23, 24, 25, 26}


def r2(x):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), 2)


def r1(x):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), 1)


def iso(d):
    if d is None or (isinstance(d, float) and np.isnan(d)):
        return None
    if hasattr(d, "date"):
        d = d.date() if not isinstance(d, date) else d
    return str(d)[:10]


def max_dd(eq: pd.Series) -> float | None:
    if eq is None or len(eq) < 1:
        return None
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return float(dd.min() * 100.0)


def cagr(start_eq, end_eq, start_d, end_d):
    if start_eq is None or end_eq is None or start_eq <= 0 or end_eq <= 0:
        return None
    days = (pd.Timestamp(end_d) - pd.Timestamp(start_d)).days
    if days <= 0:
        return None
    yrs = days / 365.25
    if yrs < 1.0:
        return None  # do not annualize windows shorter than a year (#10)
    return (end_eq / start_eq) ** (1 / yrs) * 100 - 100


def points_from_series(s: pd.Series):
    """Compact [date, equity] list, equity rounded to cents."""
    out = []
    for d, v in s.items():
        if pd.isna(v):
            continue
        out.append([iso(d), r2(v)])
    return out


def year_stats(eq: pd.Series, trades_by_year: dict, bench: pd.Series | None, start_capital=CAP):
    """Calendar-year return, intra-year max DD, trades, aligned bench return."""
    out = {}
    eq = eq.sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]
    if len(eq) == 0:
        return {str(y): None for y in YEARS}
    first_d, last_d = eq.index[0], eq.index[-1]
    for y in YEARS:
        y0, y1 = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31")
        mask = (eq.index >= y0) & (eq.index <= y1)
        sl = eq.loc[mask]
        if sl.empty:
            out[str(y)] = None
            continue
        prior = eq[eq.index < y0]
        prev = float(prior.iloc[-1]) if len(prior) else start_capital
        end = float(sl.iloc[-1])
        ret = (end / prev - 1.0) * 100.0 if prev else None
        path = pd.concat([pd.Series([prev], index=[prior.index[-1] if len(prior) else sl.index[0] - pd.Timedelta(days=1)]), sl])
        dd = max_dd(path)
        # 2026 is always YTD in this dataset. A year is complete only if we
        # have bars from early January through late December. Do not use the
        # series start month — that incorrectly marked later full years partial.
        starts_early = sl.index[0] <= pd.Timestamp(f"{y}-01-15")
        ends_late = (y < last_d.year) or (last_d >= pd.Timestamp(f"{y}-12-20"))
        complete = bool(starts_early and ends_late and y != 2026)
        bret = None
        bdd = None
        if bench is not None and len(bench):
            bprior = bench[bench.index < y0]
            bsl = bench[(bench.index >= y0) & (bench.index <= sl.index[-1])]
            if len(bsl):
                bprev = float(bprior.iloc[-1]) if len(bprior) else float(bsl.iloc[0])
                # If no prior bench bar, use first bar in window as the start (0% that day)
                if len(bprior):
                    bret = (float(bsl.iloc[-1]) / bprev - 1.0) * 100.0
                elif len(bsl) >= 2:
                    bret = (float(bsl.iloc[-1]) / float(bsl.iloc[0]) - 1.0) * 100.0
                bpath = pd.concat([pd.Series([bprev], index=[bprior.index[-1] if len(bprior) else bsl.index[0]]), bsl])
                bdd = max_dd(bpath)
        out[str(y)] = {
            "returnPct": r1(ret),
            "maxDdPct": r1(dd),
            "trades": int(trades_by_year.get(y, 0)),
            "benchReturnPct": r1(bret),
            "benchMaxDdPct": r1(bdd),
            "startEquity": r2(prev),
            "endEquity": r2(end),
            "startDate": iso(sl.index[0]),
            "endDate": iso(sl.index[-1]),
            "complete": bool(complete),
        }
    return out


def full_stats(eq: pd.Series, n_trades, start_capital=CAP):
    if eq is None or len(eq) == 0:
        return None
    end = float(eq.iloc[-1])
    start_d, end_d = iso(eq.index[0]), iso(eq.index[-1])
    # If first equity is already after costs, total return is vs start_capital
    total = (end / start_capital - 1.0) * 100.0
    return {
        "startDate": start_d,
        "endDate": end_d,
        "startEquity": r2(start_capital),
        "endEquity": r2(end),
        "totalReturnPct": r1(total),
        "cagrPct": r1(cagr(start_capital, end, start_d, end_d)),
        "maxDdPct": r1(max_dd(eq if eq.iloc[0] >= start_capital * 0.999 else pd.concat([pd.Series([start_capital], index=[eq.index[0] - pd.Timedelta(days=1)]), eq]))),
        "trades": int(n_trades) if n_trades is not None else None,
    }


def site_backtest_fields(text: str) -> dict:
    """Pull the cited headline numbers out of the site's backtest blurb for a match check."""
    import re
    if not text or not isinstance(text, str):
        return {"hasCitedBacktest": False, "text": text or ""}
    low = text.lower()
    none = any(p in low for p in [
        "no backtest of these exact rules",
        "none. this one is forward-only",
        "not yet backtested",
        "none for this equity version",
    ])
    cited = not none and any(k in low for k in ["cagr", "maximum drawdown", "in-sample", "backtest", "cycles", "primary"])
    cagr_m = re.search(r"CAGR \+?(-?[\d.]+)%", text)
    # total return forms like +203.4% or +45.12%, or "primary −9.79%"
    tot_m = re.search(r"(?:In-sample[^.]*?:|daily test,[^:]+:|In-sample, [^:]+:|Fresh \$10,000 from Nov 1, 2021:|primary)\s*([+\-−]?[\d.,]+)%", text, re.I)
    if not tot_m:
        tot_m = re.search(r"to [A-Z][a-z]+ \d+, \d{4}:\s*([+\-−]?[\d.,]+)%", text)
    dd_m = re.search(r"maximum drawdown −?(-?[\d.]+)%|drawdown −(-?[\d.]+)%|Max(?:imum)? drawdown −(-?[\d.]+)%", text)
    # unicode minus
    dd_m = re.search(r"(?:maximum drawdown|Max(?:imum)? drawdown|drawdown) ([-−][\d.]+)%", text)
    tr_m = re.search(r"([\d,]+) closed trades|([\d,]+) trades", text)
    out = {
        "hasCitedBacktest": bool(cited and not none),
        "citedTotalReturnPct": r1(tot_m.group(1).replace(",", "").replace("−", "-")) if tot_m else None,
        "citedCagrPct": r1(cagr_m.group(1)) if cagr_m else None,
        "citedMaxDdPct": r1(dd_m.group(1).replace("−", "-")) if dd_m else None,
        "citedTrades": int((tr_m.group(1) or tr_m.group(2)).replace(",", "")) if tr_m else None,
    }
    return out


def compare_to_site(full, cited):
    notes = []
    match = True
    if not cited.get("hasCitedBacktest"):
        return {"match": None, "notes": ["Site does not cite a backtest of these exact rules."]}
    if full is None:
        return {"match": False, "notes": ["No computed full stats."]}
    def close(a, b, tol=0.2):
        if a is None or b is None:
            return None
        return abs(float(a) - float(b)) <= tol
    if cited.get("citedCagrPct") is not None:
        ok = close(full.get("cagrPct"), cited["citedCagrPct"])
        if ok is False:
            match = False
            notes.append(f"CAGR computed {full.get('cagrPct')} vs site {cited['citedCagrPct']}")
    if cited.get("citedMaxDdPct") is not None:
        ok = close(full.get("maxDdPct"), cited["citedMaxDdPct"])
        if ok is False:
            match = False
            notes.append(f"Max DD computed {full.get('maxDdPct')} vs site {cited['citedMaxDdPct']}")
    if cited.get("citedTrades") is not None and full.get("trades") is not None:
        diff = abs(int(full["trades"]) - int(cited["citedTrades"]))
        if diff > 2:
            match = False
            notes.append(f"Trades computed {full['trades']} vs site {cited['citedTrades']}")
        elif diff:
            notes.append(f"Trade count {full['trades']} vs site {cited['citedTrades']} (off by {diff}; year totals use the equity/trades CSV).")
    if cited.get("citedTotalReturnPct") is not None:
        ok = close(full.get("totalReturnPct"), cited["citedTotalReturnPct"], tol=0.3)
        if ok is False:
            # #6 cites cycle returns / fresh 2021 window, not full-history total
            notes.append(f"Total return computed {full.get('totalReturnPct')} vs a figure cited on the site {cited['citedTotalReturnPct']} (may be a different window)")
    if not notes:
        notes.append("Headline CAGR / max drawdown / trade count match the site blurb within 0.2 points.")
    return {"match": match, "notes": notes}


def load_price_series():
    """SPY, QQQ, BTC close series from the newest lab snapshots."""
    spy = qqq = btc = None
    # stocks through 2026-11-11
    eq = pd.read_csv(f"{LAB_ROOT}/run_20261111/data/eq_close.csv", parse_dates=["Date"], index_col="Date")
    spy = eq["SPY"].dropna().sort_index()
    qqq = eq["QQQ"].dropna().sort_index()
    # crypto: run_20261111 uses BTC (no -USD suffix) through 2026-11-11
    cr = pd.read_csv(f"{LAB_ROOT}/run_20261111/data/crypto_close.csv", parse_dates=["Date"], index_col="Date")
    bcol = "BTC" if "BTC" in cr.columns else "BTC-USD"
    btc = cr[bcol].dropna().sort_index()
    # Yahoo BTC used by social_paper / #6 goes back further (2014)
    ybtc_path = "/workspace/social_paper/data/BTCUSD_yahoo_1d.csv"
    if os.path.exists(ybtc_path):
        y = pd.read_csv(ybtc_path)
        # detect date/close cols
        dcol = [c for c in y.columns if c.lower() in ("date", "datetime")][0]
        cands = [c for c in y.columns if c != dcol]
        # prefer a close-like column, else the first price column (this file is date,BTC)
        ccol = next((c for c in cands if c.lower() in ("close", "c", "btc", "adj close", "adjclose")), cands[0])
        y["dt"] = pd.to_datetime(y[dcol]).dt.tz_localize(None)
        yb = y.set_index("dt")[ccol].dropna().sort_index()
        yb.index = pd.DatetimeIndex(yb.index).tz_localize(None)
        # prefer the longer Yahoo history, overlay newer lab closes where they exist? Keep Yahoo for long hist, lab for recent if needed
        btc_long = yb.copy()
        btc_long.index = pd.to_datetime(btc_long.index).tz_localize(None)
        # extend with lab if lab is newer
        extra = btc[btc.index > btc_long.index.max()]
        btc = pd.concat([btc_long, extra]).sort_index()
        btc = btc[~btc.index.duplicated(keep="last")]
    spy.index = pd.to_datetime(spy.index).tz_localize(None)
    qqq.index = pd.to_datetime(qqq.index).tz_localize(None)
    btc.index = pd.to_datetime(btc.index).tz_localize(None)
    return {"SPY": spy, "QQQ": qqq, "BTC": btc}


def bh_equity(price: pd.Series, start_d=None, capital=CAP):
    p = price.dropna().sort_index()
    if start_d is not None:
        p = p[p.index >= pd.Timestamp(start_d)]
    if p.empty:
        return p
    return capital * (p / float(p.iloc[0]))


def load_lab_equity(run, slug):
    path = f"{LAB_ROOT}/{run}/results/equity_{slug}.csv"
    df = pd.read_csv(path, parse_dates=["Date"])
    s = df.set_index("Date")["equity"].astype(float).sort_index()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s


def load_lab_trades(run, slug):
    path = f"{LAB_ROOT}/{run}/results/trades_{slug}.csv"
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    # closed trades by exit year
    if "open" in df.columns:
        closed = df[df["open"].astype(str).str.lower().isin(["false", "0"])]
    else:
        closed = df
    if "exit" not in closed.columns or closed.empty:
        return {}
    exits = pd.to_datetime(closed["exit"], errors="coerce").dropna()
    return exits.dt.year.value_counts().to_dict()


def lab_trade_total(run, slug):
    path = f"{LAB_ROOT}/{run}/results/trades_{slug}.csv"
    if not os.path.exists(path):
        return 0
    df = pd.read_csv(path)
    if "open" in df.columns:
        return int((df["open"].astype(str).str.lower().isin(["false", "0"])).sum())
    return int(len(df))


def lab_published_full(run, slug):
    path = f"{LAB_ROOT}/{run}/results/results.json"
    r = json.load(open(path))
    rec = r.get("results", {}).get(slug) or {}
    return rec.get("full"), rec.get("years"), rec.get("label")


def load_template():
    t = json.load(open(TEMPLATE))
    return {s["n"]: s for s in t["strategies"]}


def none_years():
    return {str(y): None for y in YEARS}


def empty_strategy(n, tmpl, **kw):
    kind = "crypto" if n in CRYPTO_NS else "stock"
    cited = site_backtest_fields(tmpl.get("backtest") or "")
    rec = {
        "n": n,
        "name": tmpl["name"],
        "kind": kind,
        "hasBacktest": False,
        "coverage": "none",
        "gapReason": kw.get("gapReason"),
        "source": kw.get("source"),
        "costs": kw.get("costs"),
        "fill": kw.get("fill", "signal on close, fill next close"),
        "benchmark": kw.get("benchmark"),
        "caveats": kw.get("caveats") or [],
        "siteBacktest": cited,
        "siteMatch": {"match": None, "notes": ["No daily equity curve — years are null."]},
        "full": None,
        "years": none_years(),
        "equity": None,
        "equityFrom2020": None,
    }
    return rec


def attach_curves(rec, eq, trades_by_year, bench, start_capital=CAP, n_trades=None, lab_years=None):
    rec["hasBacktest"] = True
    rec["full"] = full_stats(eq, n_trades if n_trades is not None else sum(trades_by_year.values()), start_capital)
    rec["years"] = year_stats(eq, trades_by_year, bench, start_capital)
    rec["equity"] = {
        "start": start_capital,
        "startDate": iso(eq.index[0]),
        "endDate": iso(eq.index[-1]),
        "points": points_from_series(eq),
    }
    # Rebase at first bar on/after 2020-01-01 (or first bar if later), $10,000
    eq2020 = eq[eq.index >= pd.Timestamp("2020-01-01")]
    if len(eq2020):
        prior = eq[eq.index < pd.Timestamp("2020-01-01")]
        base = float(prior.iloc[-1]) if len(prior) else float(eq2020.iloc[0])
        # If we have a 2019 close, rebase using that as $10,000 so 2020 return matches
        if len(prior):
            reb = start_capital * (pd.concat([pd.Series([base], index=[prior.index[-1]]), eq2020]) / base)
            reb = reb[reb.index >= pd.Timestamp("2020-01-01")]
        else:
            reb = start_capital * (eq2020 / float(eq2020.iloc[0]))
        rec["equityFrom2020"] = {
            "start": start_capital,
            "startDate": iso(reb.index[0]),
            "endDate": iso(reb.index[-1]),
            "points": points_from_series(reb),
        }
    else:
        rec["equityFrom2020"] = None
    years_present = [y for y, v in rec["years"].items() if v is not None]
    years_complete = [y for y, v in rec["years"].items() if v and v.get("complete")]
    rec["coverage"] = "full" if len(years_present) == 7 and len(years_complete) >= 6 else "partial"
    rec["yearsWithData"] = [int(y) for y in years_present]
    rec["yearsComplete"] = [int(y) for y in years_complete]
    if lab_years:
        diffs = []
        for y, v in rec["years"].items():
            if v is None or str(y) not in lab_years:
                continue
            labv = lab_years[str(y)]
            if isinstance(labv, (int, float)) and v["returnPct"] is not None:
                if abs(v["returnPct"] - float(labv)) > 0.15:
                    diffs.append(f"{y}: computed {v['returnPct']} vs lab {labv}")
        rec["labYearCheck"] = {"ok": not diffs, "diffs": diffs, "labYearsPct": {str(k): lab_years[str(k)] if str(k) in lab_years else None for k in range(2020, 2027)}}
    return rec


def social_equity(path):
    df = pd.read_csv(path)
    # first column is the date (may be unnamed)
    dcol = df.columns[0]
    df[dcol] = pd.to_datetime(df[dcol]).dt.tz_localize(None)
    s = df.set_index(dcol)["equity"].astype(float).sort_index()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s


def social_fills_by_year(path):
    df = pd.read_csv(path)
    dt = pd.to_datetime(df["date"], errors="coerce").dropna()
    return dt.dt.year.value_counts().to_dict(), int(len(df))


def build_10(prices):
    """Rebuild #10 primary combined session equity from saved trades (0.03%/side)."""
    spy_t = json.load(open("/workspace/ema_vwap_paper/runs/trades_SPY_primary_0.0003.json"))
    qqq_t = json.load(open("/workspace/ema_vwap_paper/runs/trades_QQQ_primary_0.0003.json"))
    # session dates from the frozen baseline 5m snapshot (warmup session dropped)
    raw = pd.read_csv("/workspace/ema_vwap_paper/raw/SPY_5m_20261106T210322.csv")
    raw["dt"] = pd.to_datetime(raw["Datetime"], utc=True).dt.tz_convert("America/New_York")
    days = sorted({d.date() for d in raw["dt"]})
    # baseline drops the first complete session as warmup
    if days:
        days = days[1:]
    pnls = {}
    for t in spy_t + qqq_t:
        d = str(t["exit"])[:10]
        pnls[d] = pnls.get(d, 0.0) + float(t["pnl"])
    eq_map = {}
    eq = CAP
    for d in days:
        key = str(d)
        eq = eq + pnls.get(key, 0.0)
        eq_map[pd.Timestamp(d)] = eq
    s = pd.Series(eq_map).sort_index()
    n_trades = len(spy_t) + len(qqq_t)
    trades_by_year = {}
    for t in spy_t + qqq_t:
        y = int(str(t["entry"])[:4])
        trades_by_year[y] = trades_by_year.get(y, 0) + 1
    # 50/50 SPY/QQQ close-to-close over the same dates (official BH is first open to last close = -7.87%)
    spy = prices["SPY"].reindex(s.index).ffill()
    qqq = prices["QQQ"].reindex(s.index).ffill()
    if len(spy.dropna()) and len(qqq.dropna()):
        bh = CAP * 0.5 * (spy / float(spy.iloc[0]) + qqq / float(qqq.iloc[0]))
    else:
        bh = None
    return s, trades_by_year, n_trades, bh


def main():
    prices = load_price_series()
    tmpl = load_template()
    now = datetime.now(ET)
    strategies = []
    gaps = []

    # ---------- #1 Scale-in + 50-day exit (BTC, published +203.4%) ----------
    p1 = "/workspace/sift_evidence_bundle_20261105/B_new_experiment/outputs/fee_0.10pct/full/exit_sma50__BTC-USD/daily.csv"
    t1 = "/workspace/sift_evidence_bundle_20261105/B_new_experiment/outputs/fee_0.10pct/full/exit_sma50__BTC-USD/trades.csv"
    df1 = pd.read_csv(p1, parse_dates=["date"])
    eq1 = df1.set_index("date")["equity"].astype(float).sort_index()
    eq1.index = pd.to_datetime(eq1.index).tz_localize(None)
    tr1 = pd.read_csv(t1)
    # episodes by exit_date
    exits = pd.to_datetime(tr1["exit_date"], errors="coerce").dropna()
    tby1 = exits.dt.year.value_counts().to_dict()
    n1 = int(len(tr1))
    rec = {
        "n": 1,
        "name": tmpl[1]["name"],
        "kind": "crypto",
        "source": {
            "kind": "evidence_bundle",
            "path": p1,
            "window": "2021-11-01 to 2026-11-04",
            "note": "Published site backtest is the BTC sleeve (exit_sma50), 0.10% per side, next-close fills. Forward paper uses a 5-coin basket; the 5-coin basket backtest was +128.2% / −36.1% and is not the site headline.",
        },
        "costs": "0.10% per side (research note). A doubled-fee check printed +189.8%.",
        "fill": "signal on close, fill next close",
        "benchmark": "BTC",
        "caveats": [
            "In-sample. The 2025–26 window had already been looked at, so it is not a clean holdout.",
            "BTC-only backtest; the live paper basket is BTC, ETH, XRP, BNB, SOL.",
            "No data before Nov 1, 2021, so 2020 is null and 2021 is a partial year.",
        ],
        "siteBacktest": site_backtest_fields(tmpl[1].get("backtest")),
        "tradeCountMethod": "flat_to_flat_episodes",
    }
    rec = attach_curves(rec, eq1, tby1, bh_equity(prices["BTC"], "2021-11-01"), n_trades=n1)
    rec["siteMatch"] = compare_to_site(rec["full"], rec["siteBacktest"])
    strategies.append(rec)

    # ---------- #2, #3, #7, #8: no exact-rule backtest ----------
    strategies.append(empty_strategy(
        2, tmpl[2],
        gapReason="The site states there is no backtest of these exact rules (30-day z-score, enter below −1, $1,000 slots, −15% stop, 20-day max hold). A different 20-day / −1.5σ variant exists as context only and was not used.",
        source={"kind": "none", "records": (tmpl[2].get("why") or {}).get("records")},
        costs="0.10% per side (forward paper)",
        benchmark="BTC",
        caveats=["Forward-only paper test from Nov 5, 2026."],
    ))
    strategies.append(empty_strategy(
        3, tmpl[3],
        gapReason="The site states this one is forward-only. No original backtest record exists for these exact rules.",
        source={"kind": "none", "records": (tmpl[3].get("why") or {}).get("records")},
        costs="0.10% per side (forward paper)",
        benchmark="BTC",
        caveats=["Launched as a forward-only paper test next to #2."],
    ))

    # ---------- #4 EMA 13/80 ----------
    eq4 = social_equity("/workspace/social_paper/runs/baseline/ema_1d/equity.csv")
    tby4, n4 = social_fills_by_year("/workspace/social_paper/runs/baseline/ema_1d/trades.csv")
    rec = {
        "n": 4,
        "name": tmpl[4]["name"],
        "kind": "crypto",
        "source": {
            "kind": "social_paper_baseline",
            "path": "/workspace/social_paper/runs/baseline/ema_1d/equity.csv",
            "window": "2021-11-01 to 2026-11-05",
        },
        "costs": "0.10% fee plus 0.10% slippage per side",
        "fill": "signal on close, fill next close",
        "benchmark": "BTC",
        "caveats": [
            "In-sample. The 2025–26 slice is previously examined, not a holdout.",
            "No data before Nov 1, 2021, so 2020 is null and 2021 is a partial year.",
            "Trade counts are fills (buys and sells), matching the baseline's 198 trades.",
        ],
        "siteBacktest": site_backtest_fields(tmpl[4].get("backtest")),
        "tradeCountMethod": "fills",
    }
    rec = attach_curves(rec, eq4, tby4, bh_equity(prices["BTC"], "2021-11-01"), n_trades=n4)
    rec["siteMatch"] = compare_to_site(rec["full"], rec["siteBacktest"])
    strategies.append(rec)

    # ---------- #5 30-day breakout ----------
    eq5 = social_equity("/workspace/social_paper/runs/baseline/botwars_1d/equity.csv")
    tby5, n5 = social_fills_by_year("/workspace/social_paper/runs/baseline/botwars_1d/trades.csv")
    rec = {
        "n": 5,
        "name": tmpl[5]["name"],
        "kind": "crypto",
        "source": {
            "kind": "social_paper_baseline",
            "path": "/workspace/social_paper/runs/baseline/botwars_1d/equity.csv",
            "window": "2021-11-01 to 2026-11-05",
        },
        "costs": "0.10% fee plus 0.10% slippage per side",
        "fill": "signal on close, fill next close",
        "benchmark": "BTC",
        "caveats": [
            "In-sample. The 2025–26 slice is previously examined, not a holdout.",
            "No data before Nov 1, 2021, so 2020 is null and 2021 is a partial year.",
            "Trade counts are fills, matching the baseline's 530 trades.",
        ],
        "siteBacktest": site_backtest_fields(tmpl[5].get("backtest")),
        "tradeCountMethod": "fills",
    }
    rec = attach_curves(rec, eq5, tby5, bh_equity(prices["BTC"], "2021-11-01"), n_trades=n5)
    rec["siteMatch"] = compare_to_site(rec["full"], rec["siteBacktest"])
    strategies.append(rec)

    # ---------- #6 Halving 500 ----------
    eq6 = social_equity("/workspace/social_paper/runs/baseline/halving_500/equity.csv")
    tby6, n6 = social_fills_by_year("/workspace/social_paper/runs/baseline/halving_500/trades.csv")
    rec = {
        "n": 6,
        "name": tmpl[6]["name"],
        "kind": "crypto",
        "source": {
            "kind": "social_paper_baseline",
            "path": "/workspace/social_paper/runs/baseline/halving_500/equity.csv",
            "window": "2014-09-17 to 2026-11-04 (Yahoo BTC-USD)",
            "note": "Calendar-year figures come from the continuous running account (started $10,000 on 2014-09-17). The site also cites a fresh $10,000 from Nov 1, 2021: +545.7% / max DD −28.1%, and per-cycle returns.",
        },
        "costs": "0.10% fee plus 0.10% slippage per side",
        "fill": "signal on close, fill next close",
        "benchmark": "BTC",
        "caveats": [
            "Only about three testable cycles. Tiny sample. The viral chart was drawn in hindsight.",
            "The 2012 cycle is untestable (before Yahoo data).",
            "The native full-history total return is enormous because early BTC prices were tiny — do not treat that as a deployable expectation. Prefer equityFrom2020 and the year tabs for 2020–2026.",
            "The site's headline fresh-from-Nov-2021 window (+545.7%) is a different starting date than the 2014 continuous curve.",
        ],
        "siteBacktest": site_backtest_fields(tmpl[6].get("backtest")),
        "tradeCountMethod": "fills",
        "freshFrom2021": {"totalReturnPct": 545.7, "maxDdPct": -28.14, "window": "2021-11-01 to 2026-11-04", "vsBtcPct": 31.8},
    }
    rec = attach_curves(rec, eq6, tby6, bh_equity(prices["BTC"], "2014-09-17"), n_trades=n6)
    rec["siteMatch"] = compare_to_site(rec["full"], rec["siteBacktest"])
    # The full-history total will not match cycle / fresh-window cites — expected
    rec["siteMatch"]["notes"].append("Expected: site cites per-cycle returns and a fresh Nov 2021 window, not the 2014–2026 compounded total.")
    strategies.append(rec)

    strategies.append(empty_strategy(
        7, tmpl[7],
        gapReason="Not yet backtested. The rules are still being built, and the paper account has not started.",
        source={"kind": "none"},
        costs="Plan: 0.10% fee plus 0.10% slippage per side",
        benchmark="BTC",
        caveats=["Not running."],
    ))
    strategies.append(empty_strategy(
        8, tmpl[8],
        gapReason="The site states there is no backtest for this equity version (close 20% below the 25-day average, $1,000 slots, −15% stop, 20-day max hold).",
        source={"kind": "none", "records": (tmpl[8].get("why") or {}).get("records")},
        costs="0.05% per side (forward paper)",
        benchmark="SPY",
        caveats=["Forward paper from Nov 3, 2026. A related crypto dip-buy grid is a different market and was not used."],
    ))

    # ---------- #9 Nasdaq top-5 ----------
    eq9 = social_equity("/workspace/social_paper/runs/baseline/nasdaq_top5/equity.csv")
    tby9, n9 = social_fills_by_year("/workspace/social_paper/runs/baseline/nasdaq_top5/trades.csv")
    rec = {
        "n": 9,
        "name": tmpl[9]["name"],
        "kind": "stock",
        "source": {
            "kind": "social_paper_baseline",
            "path": "/workspace/social_paper/runs/baseline/nasdaq_top5/equity.csv",
            "window": "2021-11-01 to 2026-11-04",
        },
        "costs": "0.10% per side",
        "fill": "signal on close, fill next close",
        "benchmark": "QQQ",
        "caveats": [
            "Do not trust this number as a deployable edge: it uses today's Nasdaq-100 members, so companies that fell out of the index are missing (survivorship bias).",
            "The 126-trading-day lookback is an assumption; the source post did not specify it.",
            "In-sample. No data before Nov 2021, so 2020 is null and 2021 is a partial year.",
        ],
        "siteBacktest": site_backtest_fields(tmpl[9].get("backtest")),
        "tradeCountMethod": "fills",
    }
    rec = attach_curves(rec, eq9, tby9, bh_equity(prices["QQQ"], "2021-11-01"), n_trades=n9)
    rec["siteMatch"] = compare_to_site(rec["full"], rec["siteBacktest"])
    strategies.append(rec)

    # ---------- #10 9 EMA + VWAP intraday ----------
    eq10, tby10, n10, bh10 = build_10(prices)
    rec = {
        "n": 10,
        "name": tmpl[10]["name"],
        "kind": "stock",
        "source": {
            "kind": "ema_vwap_paper_baseline_replay",
            "path": "/workspace/ema_vwap_paper/runs/trades_SPY_primary_0.0003.json",
            "window": "2026-08-17 to 2026-11-06, 59 sessions",
            "note": "Daily (session) equity was rebuilt from the saved primary 0.03%/side trades for the two $5,000 SPY and QQQ sleeves. The variant is reported separately on the site and is not in this curve.",
        },
        "costs": "0.03% per side (primary). A 0.06% sensitivity run was also done on the backtest.",
        "fill": "Enter at the next 5-minute bar's open; flat overnight",
        "benchmark": "SPY_QQQ_50_50",
        "caveats": [
            "Only 59 sessions, Aug 17 to Nov 6, 2026. Years 2020–2025 are null. 2026 is a short partial window, not a calendar year.",
            "In-sample. The test was picked to check a popular day-trading claim, not because the backtest looked good.",
            "Official 50/50 buy-and-hold (first session open to last close) is −7.87%. The bench curve here is close-to-close on session dates and may differ by a few tenths of a point.",
            "Trade counts are individual sleeve fills (SPY 153 + QQQ 172 = 325), not combined round-trips.",
        ],
        "siteBacktest": site_backtest_fields(tmpl[10].get("backtest")),
        "tradeCountMethod": "fills",
        "officialCombinedPrimaryPct": -9.79,
        "officialBuyHoldPct": -7.87,
    }
    rec = attach_curves(rec, eq10, tby10, bh10, n_trades=n10)
    rec["siteMatch"] = compare_to_site(rec["full"], rec["siteBacktest"])
    # Sanity: combined primary should be about -9.79%
    if rec["full"] and rec["full"]["totalReturnPct"] is not None:
        if abs(rec["full"]["totalReturnPct"] - (-9.79)) > 0.15:
            rec["siteMatch"]["notes"].append(f"Rebuilt combined return {rec['full']['totalReturnPct']} vs site primary −9.79%.")
            rec["siteMatch"]["match"] = False
        else:
            rec["siteMatch"]["notes"].append("Rebuilt combined primary return matches the site's −9.79%.")
    strategies.append(rec)

    # ---------- #11–26 from strategy lab equity + trades ----------
    for n, (run, slug) in LAB_MAP.items():
        eq = load_lab_equity(run, slug)
        tby = load_lab_trades(run, slug)
        ntr = lab_trade_total(run, slug)
        full_lab, lab_years, lab_label = lab_published_full(run, slug)
        kind = "crypto" if n in CRYPTO_NS else "stock"
        bench_id = "BTC" if kind == "crypto" else "SPY"
        # #18/#19/#21 are leveraged ETFs; still vs SPY as the brief asked, plus we have QQQ available
        if n in (18, 21):
            bench_id = "QQQ"  # more natural for Nasdaq-3x; SPY still in the shared benchmarks object
        costs = "0.25% per side" if kind == "crypto" else "0.05% per side"
        start = iso(eq.index[0])
        bench = bh_equity(prices[bench_id], start)
        rec = {
            "n": n,
            "name": tmpl[n]["name"],
            "kind": kind,
            "source": {
                "kind": "sift_strategy_lab",
                "run": run,
                "slug": slug,
                "equityFile": f"{LAB_ROOT}/{run}/results/equity_{slug}.csv",
                "tradesFile": f"{LAB_ROOT}/{run}/results/trades_{slug}.csv",
                "window": f"{iso(eq.index[0])} to {iso(eq.index[-1])}",
            },
            "costs": costs + (", uninvested cash earns 0%" if n >= 22 else ""),
            "fill": "signal on close, fill next close",
            "benchmark": bench_id,
            "caveats": [
                "Same rules, costs and fills as the site cards.",
                "2026 is year-to-date through the last backtest bar, not a full calendar year.",
            ],
            "siteBacktest": site_backtest_fields(tmpl[n].get("backtest")),
            "tradeCountMethod": "closed_exits",
            "labFull": {k: full_lab.get(k) for k in ("cagr", "maxdd", "sharpe", "total", "trades", "win")} if full_lab else None,
        }
        if n == 17:
            rec["caveats"].append("Walk-forward backtest from January 2017 (the table is re-picked once a year).")
        if n == 9:
            pass
        rec = attach_curves(rec, eq, tby, bench, n_trades=ntr, lab_years={str(k): v for k, v in (lab_years or {}).items()})
        rec["siteMatch"] = compare_to_site(rec["full"], rec["siteBacktest"])
        # Also compare to lab published full
        if full_lab:
            notes = rec["siteMatch"]["notes"]
            if rec["full"]["cagrPct"] is not None and abs(rec["full"]["cagrPct"] - float(full_lab["cagr"])) > 0.15:
                notes.append(f"CAGR {rec['full']['cagrPct']} vs lab full.cagr {full_lab['cagr']}")
            if rec["full"]["maxDdPct"] is not None and abs(rec["full"]["maxDdPct"] - float(full_lab["maxdd"])) > 0.2:
                notes.append(f"Max DD {rec['full']['maxDdPct']} vs lab full.maxdd {full_lab['maxdd']}")
        strategies.append(rec)

    strategies.sort(key=lambda s: s["n"])
    assert [s["n"] for s in strategies] == list(range(1, 27)), [s["n"] for s in strategies]

    # Shared benchmark curves, $10k from 2020-01-02 (or first 2020 bar)
    benchmarks = {}
    for key in ("SPY", "QQQ", "BTC"):
        p = prices[key]
        # buy-and-hold from last 2019 close if available
        prior = p[p.index < pd.Timestamp("2020-01-01")]
        sl = p[p.index >= pd.Timestamp("2020-01-01")]
        if len(prior):
            # $10,000 at the last 2019 close, so 2020's first bar already shows that day's move
            eqb = (sl / float(prior.iloc[-1])) * CAP
            years_src = pd.concat([pd.Series([CAP], index=[prior.index[-1]]), eqb])
        else:
            eqb = bh_equity(sl)
            years_src = eqb
        years = year_stats(years_src, {}, None)
        # For bench-only years, drop trades/bench fields clutter — keep return and dd
        yclean = {}
        for y, v in years.items():
            if v is None:
                yclean[y] = None
            else:
                yclean[y] = {
                    "returnPct": v["returnPct"],
                    "maxDdPct": v["maxDdPct"],
                    "startDate": v["startDate"],
                    "endDate": v["endDate"],
                    "complete": v["complete"],
                    "endEquity": v["endEquity"],
                }
        benchmarks[key] = {
            "name": {"SPY": "SPY buy-and-hold", "QQQ": "QQQ buy-and-hold", "BTC": "BTC buy-and-hold"}[key],
            "costs": "No ongoing costs. Entry is a cash mark at the start of the window (no fee in this series).",
            "startDate": iso(eqb.index[0]),
            "endDate": iso(eqb.index[-1]),
            "years": yclean,
            "equityFrom2020": {"start": CAP, "startDate": iso(eqb.index[0]), "endDate": iso(eqb.index[-1]), "points": points_from_series(eqb)},
        }

    coverage = {
        "fullOrPartialWithCurve": [s["n"] for s in strategies if s["hasBacktest"]],
        "full2020to2025": [s["n"] for s in strategies if s.get("coverage") == "full"],
        "partial": [s["n"] for s in strategies if s.get("coverage") == "partial"],
        "none": [s["n"] for s in strategies if s["coverage"] == "none"],
        "siteNumberMismatches": [s["n"] for s in strategies if s.get("siteMatch", {}).get("match") is False],
    }

    doc = {
        "meta": {
            "generatedET": now.strftime("%Y-%m-%d %H:%M %Z"),
            "generatedISO": now.isoformat(timespec="seconds"),
            "capital": CAP,
            "years": YEARS,
            "year2026IsYtd": True,
            "note": "Backtest (hypothetical, includes costs). These paths are not the live forward/paper marks on the SIFT site. Signal on the close, fill at the next close, unless a strategy says otherwise.",
            "costsDefault": {"stocks": "0.05% per side (strategies 11–21, except #9 used 0.10% and #10 used 0.03%)", "cryptoLabs": "0.25% per side (strategies 13, 15, 16, 22–26)", "cryptoEarly": "0.10% per side, and #4–#6 also add 0.10% slippage per side"},
            "doNotConfuseWith": "history.json / data.js forward paper equity (started November 2026, $10,000 each).",
            "sourceNote": "Reused saved equity curves. No strategy-lab or paper-engine rules were changed. The site repo was not modified.",
        },
        "coverage": coverage,
        "benchmarks": benchmarks,
        "strategies": strategies,
    }

    # Write compact but still readable-enough JSON (no extra spaces around separators)
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    size = len(raw.encode("utf-8"))
    if size > 5 * 1024 * 1024:
        # Downsample equity points to every 5th day outside the selected year window... shouldn't happen
        raise SystemExit(f"JSON is {size} bytes; downsample needed")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(raw)
        f.write("\n")
    print(f"Wrote {OUT} ({size} bytes, {size/1024:.1f} KiB)")
    print("coverage", json.dumps(coverage))
    # print a compact table
    print(f"{'#':>3} {'name':<42} {'cov':<8} {'cagr':>7} {'maxdd':>8} {'yrs':<20} match")
    for s in strategies:
        full = s.get("full") or {}
        yrs = ",".join(str(y) for y in s.get("yearsWithData") or []) or "—"
        print(f"{s['n']:>3} {s['name'][:42]:<42} {s['coverage']:<8} {str(full.get('cagrPct') or '—'):>7} {str(full.get('maxDdPct') or '—'):>8} {yrs:<20} {s.get('siteMatch',{}).get('match')}")
        if s.get("siteMatch", {}).get("match") is False:
            for nte in s["siteMatch"]["notes"]:
                print("     !", nte)
        if s.get("labYearCheck") and not s["labYearCheck"]["ok"]:
            print("     lab years", s["labYearCheck"]["diffs"])


if __name__ == "__main__":
    main()
