#!/usr/bin/env python3
"""Shared helpers for the Nov 2026 new paper experiments. Paper only."""
from __future__ import annotations

import csv
import json
import math
import os
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
NY = ZoneInfo("America/New_York")
TODAY = datetime.now(NY).date()
FORWARD_START = date(2026, 11, 27)
EXPERIMENT_LABEL = "New experiment, started November 27, 2026"
CAPITAL = 10_000.0

# Desk usual: stocks 0.05%/side, crypto 0.25%/side. New tests use 1.5x.
STOCK_FEE = 0.0005 * 1.5  # 0.075%
CRYPTO_FEE = 0.0025 * 1.5  # 0.375%
GRID_FEE = 0.001 * 1.5  # strategy states 0.1%; apply 1.5x → 0.15%

CACHE = HERE / "cache"
CACHE.mkdir(parents=True, exist_ok=True)


def money(v: float) -> str:
    return f"${v:,.2f}"


def pct(v: float) -> str:
    if abs(v) < 5e-5:
        return "0.00%"
    sign = "+" if v > 0 else "−"
    return f"{sign}{abs(v) * 100:.2f}%"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def flatten_yf(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def _cache_path(key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
    return CACHE / f"{safe}.pkl"


def load_yahoo(tickers: list[str] | str, start: str = "2005-01-01") -> pd.DataFrame:
    if isinstance(tickers, str):
        tickers = [tickers]
    key = f"yf_{'_'.join(tickers)}_{start}"
    path = _cache_path(key)
    if path.exists() and time.time() - path.stat().st_mtime < 6 * 3600:
        return pd.read_pickle(path)
    raw = yf.download(tickers, start=start, progress=False, auto_adjust=True, threads=True)
    if isinstance(raw.columns, pd.MultiIndex):
        # Close panel: columns = tickers
        if "Close" in raw.columns.get_level_values(0):
            close = raw["Close"].copy()
        else:
            close = raw.copy()
            close.columns = close.columns.get_level_values(0)
    else:
        close = raw[["Close"]].copy()
        close.columns = tickers
    close = close.sort_index()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    close.to_pickle(path)
    return close


def load_yahoo_ohlc(ticker: str, start: str = "2005-01-01") -> pd.DataFrame:
    key = f"yf_ohlc_{ticker}_{start}"
    path = _cache_path(key)
    if path.exists() and time.time() - path.stat().st_mtime < 6 * 3600:
        return pd.read_pickle(path)
    raw = flatten_yf(yf.download(ticker, start=start, progress=False, auto_adjust=True))
    raw = raw.sort_index()
    raw.index = pd.to_datetime(raw.index).tz_localize(None)
    raw.to_pickle(path)
    return raw


def load_yahoo_ohlc_panel(tickers: list[str], start: str = "2005-01-01") -> dict[str, pd.DataFrame]:
    """Adjusted OHLC panels per ticker (dividend/split consistent via auto_adjust)."""
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        out[t] = load_yahoo_ohlc(t, start)
    return out


def trade_key(row: dict) -> str:
    """Stable idempotency key for a simulated fill."""
    return "|".join(
        str(row.get(k, ""))
        for k in ("timestamp", "side", "symbol", "price", "qty", "reason")
    )


def write_forward_ledger(folder: Path, equity_rows: list[dict], trades: list[dict], state: dict) -> None:
    """Overwrite forward equity/trades/state. Deterministic rewrite = no duplicate fills on re-run."""
    fwd = ensure_dir(folder / "forward")
    # Deduplicate trades by key while preserving order (safety if a runner appends).
    seen: set[str] = set()
    unique: list[dict] = []
    for t in trades:
        k = trade_key(t)
        if k in seen:
            continue
        seen.add(k)
        unique.append(t)
    write_csv(
        fwd / "equity.csv",
        equity_rows,
        fieldnames=list(equity_rows[0].keys()) if equity_rows else ["date", "equity"],
    )
    write_csv(
        fwd / "trades.csv",
        unique,
        fieldnames=["timestamp", "side", "symbol", "price", "qty", "fees", "pnl", "reason"],
    )
    write_json(fwd / "state.json", state)


def classify_status(
    *,
    as_of: str | None,
    exposure: float,
    last_signal: str | None,
    data_failure: str | None,
    category: str,
    today: date | None = None,
) -> str:
    """UI status labels required by the Paper Bots front page."""
    today = today or TODAY
    if data_failure:
        return "Data stale"
    if not as_of:
        return "Awaiting first mark"
    try:
        mark = date.fromisoformat(str(as_of)[:10])
    except ValueError:
        return "Data stale"
    # Stocks: allow weekend/holiday lag; crypto: tighter.
    max_lag = 4 if category == "Stock Strategy" else 2
    if (today - mark).days > max_lag:
        return "Data stale"
    if exposure is not None and exposure < 0.005:
        if last_signal in (None, "", "none", "no_signal", "awaiting"):
            return "No signal"
        return "In cash"
    if last_signal in ("awaiting", "awaiting_first_mark"):
        return "Awaiting first mark"
    return "Invested"


def turnover_from_trades(trades: list[dict], capital: float = CAPITAL) -> float:
    """Approximate one-way turnover as sum(|notional|) / capital / 2 over the period."""
    if not trades or capital <= 0:
        return 0.0
    notionals = []
    for t in trades:
        try:
            notionals.append(abs(float(t.get("price") or 0) * float(t.get("qty") or t.get("shares") or 0)))
        except (TypeError, ValueError):
            continue
    return float(sum(notionals) / capital / 2.0) if notionals else 0.0


def fetch_coinbase_daily(product: str = "BTC-USD", start: date | None = None) -> pd.DataFrame:
    """Daily candles from Coinbase public API. Columns: Open, High, Low, Close, Volume."""
    start = start or date(2016, 1, 1)
    key = f"cb_{product}_{start.isoformat()}"
    path = _cache_path(key)
    if path.exists() and time.time() - path.stat().st_mtime < 6 * 3600:
        return pd.read_pickle(path)

    rows: list[list[float]] = []
    end_ts = int(datetime.now(timezone.utc).timestamp())
    start_ts = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    cursor = end_ts
    url = f"https://api.exchange.coinbase.com/products/{product}/candles"
    while cursor > start_ts:
        params = {"granularity": 86400, "end": datetime.fromtimestamp(cursor, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
                  "start": datetime.fromtimestamp(max(start_ts, cursor - 86400 * 280), tz=timezone.utc).isoformat().replace("+00:00", "Z")}
        r = requests.get(url, params=params, timeout=45)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        oldest = min(c[0] for c in batch)
        if oldest >= cursor:
            break
        cursor = oldest - 1
        time.sleep(0.15)
    if not rows:
        raise RuntimeError(f"No Coinbase candles for {product}")
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df["date"] = pd.to_datetime(df["time"], unit="s")
    df = df.drop_duplicates("time").sort_values("time")
    df = df.set_index("date")[["open", "high", "low", "close", "volume"]]
    df.columns = ["Open", "High", "Low", "Close", "Volume"]
    df = df[df.index.date >= start]
    df.to_pickle(path)
    return df


def fetch_deribit_funding(currency: str = "BTC", start: date | None = None) -> pd.DataFrame:
    """8h funding interest history from Deribit public API."""
    start = start or date(2019, 1, 1)
    key = f"deribit_funding_{currency}_{start.isoformat()}"
    path = _cache_path(key)
    if path.exists() and time.time() - path.stat().st_mtime < 12 * 3600:
        return pd.read_pickle(path)
    instrument = f"{currency}-PERPETUAL"
    start_ms = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    url = "https://www.deribit.com/api/v2/public/get_funding_rate_history"
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        chunk_end = min(cursor + 90 * 86400 * 1000, end_ms)
        r = requests.get(url, params={"instrument_name": instrument, "start_timestamp": cursor, "end_timestamp": chunk_end}, timeout=45)
        r.raise_for_status()
        batch = r.json().get("result") or []
        rows.extend(batch)
        cursor = chunk_end + 1
        time.sleep(0.12)
    if not rows:
        raise RuntimeError(f"No Deribit funding for {instrument}")
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.sort_values("time").drop_duplicates("timestamp")
    df["funding"] = df["interest_8h"].astype(float)
    out = df.set_index("time")[["funding", "index_price"]]
    out.to_pickle(path)
    return out


def bil_daily_yield(close: pd.Series) -> pd.Series:
    """Approximate daily T-bill yield from BIL ETF close-to-close returns (cash proxy)."""
    rets = close.pct_change().fillna(0.0)
    # Floor negative daily noise as 0 for cash-idle proxy; BIL can tick down slightly.
    return rets.clip(lower=0.0)


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min()) if len(dd) else 0.0


def sharpe_ratio(daily_rets: pd.Series, periods: int = 252) -> float:
    r = daily_rets.dropna()
    if len(r) < 5 or r.std() == 0:
        return 0.0
    return float(np.sqrt(periods) * r.mean() / r.std())


def deflated_sharpe(sharpe: float, n_obs: int, skew: float = 0.0, kurt: float = 3.0, n_trials: int = 1) -> float:
    """Bailey & López de Prado deflated Sharpe ratio as a probability in [0, 1].

    Single frozen rule → n_trials=1 (no multiple-testing haircut beyond non-normality).
    """
    if n_obs < 10 or not math.isfinite(sharpe):
        return float("nan")
    sr = sharpe
    euler = 0.5772156649
    if n_trials <= 1:
        e_max = 0.0
    else:
        e_max = ((1 - euler) * norm_ppf(1 - 1.0 / n_trials) + euler * norm_ppf(1 - 1.0 / (n_trials * math.e)))
    se = math.sqrt((1 - skew * sr + (kurt - 1) / 4.0 * sr * sr) / max(n_obs - 1, 1))
    if se <= 0:
        return float("nan")
    z = (sr - e_max) / se
    # Φ(z)
    return float(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))


def norm_ppf(p: float) -> float:
    # Acklam approximation
    if p <= 0 or p >= 1:
        return float("nan")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068071618242e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5]) * q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def cagr(equity: pd.Series, periods_per_year: float = 252.0) -> float:
    if len(equity) < 2:
        return 0.0
    years = len(equity) / periods_per_year
    if years <= 0 or equity.iloc[0] <= 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def summarize_backtest(
    equity: pd.Series,
    trades: list[dict],
    *,
    periods_per_year: float = 252.0,
    crash_windows: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    rets = equity.pct_change().fillna(0.0)
    closed = [t for t in trades if t.get("pnl") is not None]
    wins = [t for t in closed if t["pnl"] > 0]
    avg_trade = float(np.mean([t["pnl"] for t in closed])) if closed else 0.0
    invested = (equity != equity.shift(1)).astype(float)  # rough; better use exposure if provided
    # time in market: fraction of days where not pure cash mark relative to prior cash-only — use trade open flags if present
    in_mkt = None
    if trades and any("in_market" in t for t in trades):
        pass
    out = {
        "label": "Historical backtest, not forward results",
        "start": str(equity.index[0].date()) if len(equity) else None,
        "end": str(equity.index[-1].date()) if len(equity) else None,
        "n_days": int(len(equity)),
        "final_equity": round(float(equity.iloc[-1]), 2) if len(equity) else None,
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) else None,
        "cagr": cagr(equity, periods_per_year),
        "sharpe": sharpe_ratio(rets, int(periods_per_year)),
        "deflated_sharpe": deflated_sharpe(
            sharpe_ratio(rets, int(periods_per_year)),
            len(rets),
            float(rets.skew()) if len(rets) > 5 else 0.0,
            float(rets.kurtosis() + 3) if len(rets) > 5 else 3.0,
            n_trials=1,
        ),
        "max_drawdown": max_drawdown(equity),
        "trades": len(closed),
        "win_rate": (len(wins) / len(closed)) if closed else None,
        "average_trade": avg_trade,
        "time_in_market": None,
        "over_10pct_dd": max_drawdown(equity) < -0.10,
        "crash_periods": {},
    }
    crash_windows = crash_windows or {
        "2020": ("2020-02-15", "2020-04-15"),
        "2022": ("2022-01-01", "2022-12-31"),
    }
    for name, (a, b) in crash_windows.items():
        sl = equity.loc[a:b]
        if len(sl) >= 2:
            out["crash_periods"][name] = {
                "return": float(sl.iloc[-1] / sl.iloc[0] - 1),
                "max_drawdown": max_drawdown(sl),
            }
    return out


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    ensure_dir(path.parent)
    if not rows:
        fieldnames = fieldnames or []
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
        return
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fieldnames})


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


def append_trade(path: Path, row: dict) -> None:
    ensure_dir(path.parent)
    exists = path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


@dataclass
class StrategyMeta:
    id: str
    name: str
    category: str  # Stock Strategy | Crypto Bot
    source: str
    why: str
    why_fail: str
    rules: list[str]
    benchmarks: list[str]
    fee_per_side: float
    comparisons_note: str = "comparison only, not a pick"

    def to_public(self) -> dict:
        d = asdict(self)
        d["experiment_label"] = EXPERIMENT_LABEL
        d["forward_start"] = FORWARD_START.isoformat()
        d["capital"] = CAPITAL
        d["desk_dd_limit"] = 0.10
        return d
