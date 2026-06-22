"""
Batch spot prices from Yahoo via /v7/finance/spark.

The v7 /finance/quote endpoint returns 401 without a logged-in cookie context,
and direct browser fetch() fails CORS outside Yahoo domains. Spark matches the
pattern used in src/scrapers/technical/market_overview.py and works with only
Referer + User-Agent (stdlib urllib — no extra deps in the slim server image).
"""

from __future__ import annotations

import json
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
    "Accept": "application/json",
}

_SYM_RE = re.compile(r"^[A-Z0-9.\-\^]{1,24}$")
_MAX_SYMBOLS = 20


def parse_symbols_param(symbols_csv: str) -> list[str]:
    """Uppercase tickers from a comma-separated query string; cap count; drop invalid."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols_csv.split(","):
        s = raw.strip().upper()
        if not s or s in seen:
            continue
        if not _SYM_RE.fullmatch(s):
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= _MAX_SYMBOLS:
            break
    return out


def fetch_spark_prices(symbols: list[str]) -> list[dict]:
    """
    Returns Yahoo-shaped dicts: [{"symbol": "AAPL", "regularMarketPrice": 123.45, "regularMarketChangePercent": 1.2}, ...].
    On HTTP/network failure returns [].
    """
    if not symbols:
        return []
    query = urlencode(
        {
            "symbols": ",".join(symbols),
            "range": "1d",
            "interval": "5m",
            "includePrePost": "false",
        }
    )
    url = f"{_SPARK_URL}?{query}"
    req = Request(url, headers=_HEADERS)
    try:
        with urlopen(req, context=ssl.create_default_context(), timeout=25) as resp:
            raw = resp.read().decode()
    except (HTTPError, URLError, TimeoutError, OSError):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    out: list[dict] = []
    for entry in data.get("spark", {}).get("result", []) or []:
        sym = entry.get("symbol") or ""
        responses = entry.get("response") or []
        if not sym or not responses:
            continue
        meta = responses[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            continue
        try:
            price_val = float(price)
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
            change_pct = None
            if prev is not None:
                prev_val = float(prev)
                if prev_val != 0:
                    change_pct = ((price_val - prev_val) / prev_val) * 100

            item = {
                "symbol": sym,
                "regularMarketPrice": price_val,
            }
            if change_pct is not None:
                item["regularMarketChangePercent"] = change_pct
            out.append(item)
        except (TypeError, ValueError):
            continue
    return out
