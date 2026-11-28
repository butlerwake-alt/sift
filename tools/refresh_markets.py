"""Refresh SIFT's public, USD daily closing-price snapshot."""
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ASSETS = {
    "SPY": ("S&P 500 ETF", "etf"),
    "QQQ": ("Nasdaq-100 ETF", "etf"),
    "DIA": ("Dow Jones ETF", "etf"),
    "IWM": ("Russell 2000 ETF", "etf"),
    "AAPL": ("Apple", "stocks"),
    "MSFT": ("Microsoft", "stocks"),
    "NVDA": ("Nvidia", "stocks"),
    "AMZN": ("Amazon", "stocks"),
    "GOOGL": ("Alphabet", "stocks"),
    "TSLA": ("Tesla", "stocks"),
    "BTC": ("Bitcoin", "crypto"),
    "ETH": ("Ethereum", "crypto"),
    "SOL": ("Solana", "crypto"),
    "XRP": ("XRP", "crypto"),
    "DOGE": ("Dogecoin", "crypto"),
}
DESTINATION = Path(__file__).resolve().parents[1] / "data" / "markets.json"


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def closes(symbol, kind, now):
    if kind == "crypto":
        url = f"https://api.exchange.coinbase.com/products/{symbol}-USD/candles?granularity=86400"
        rows = fetch_json(url)
        points = [(datetime.fromtimestamp(row[0], timezone.utc).date(), row[4]) for row in rows]
        # Coinbase timestamps the opening of each UTC day. Skip incomplete days.
        cutoff = now.date() - timedelta(days=1)
    else:
        today = now.astimezone(ZoneInfo("America/New_York")).date()
        query = urlencode({"assetclass": kind, "fromdate": today - timedelta(days=100),
                           "todate": today, "limit": 100})
        url = f"https://api.nasdaq.com/api/quote/{symbol}/historical?{query}"
        payload = fetch_json(url)["data"]
        if payload["symbol"] != symbol:
            raise ValueError("unexpected Nasdaq symbol")
        rows = payload["tradesTable"]["rows"]
        points = [(datetime.strptime(row["date"], "%m/%d/%Y").date(),
                   float(row["close"].replace("$", "").replace(",", ""))) for row in rows]
        cutoff = today
    valid = {day.isoformat(): price for day, price in points
             if cutoff - timedelta(days=95) <= day <= cutoff and math.isfinite(price) and price > 0}
    if len(valid) < 2:
        raise ValueError("too few closing prices")
    return sorted(valid.items())


def main():
    previous = json.loads(DESTINATION.read_text()) if DESTINATION.exists() else {"assets": {}}
    now = datetime.now(timezone.utc)
    assets = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        requests = {symbol: pool.submit(closes, symbol, kind, now)
                    for symbol, (_, kind) in ASSETS.items()}
        for symbol, request in requests.items():
            name, kind = ASSETS[symbol]
            prior = previous["assets"].get(symbol, {})
            points = prior.get("points", [])
            try:
                incoming = request.result()
                if points and incoming[-1][0] < points[-1][0]:
                    raise ValueError("provider returned an older close")
                points = incoming
            except Exception as error:
                print(f"{symbol}: keeping previous closes ({error})")
            assets[symbol] = {"name": name, "kind": kind, "points": points}
    if not any(asset["points"] for asset in assets.values()):
        raise SystemExit("No market data available")
    temporary = DESTINATION.with_suffix(".tmp")
    temporary.write_text(json.dumps({"assets": assets}, indent=2) + "\n")
    temporary.replace(DESTINATION)


if __name__ == "__main__":
    main()
