"""
Build the market_compare section — benchmark prices captured at report time so
the report card can later show "journal date close vs live" deltas the same way
the company cards do.
"""

from __future__ import annotations

from curl_cffi import requests as cf_requests

from src.pipelines.build_report.models import BenchmarkQuote

_SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
    "Accept": "application/json",
}

_BENCHMARKS: list[tuple[str, str]] = [
    ("VWCE.DE", "VWCE (FTSE All-World)"),
    ("SPY", "SPY (S&P 500)"),
]


def _fetch_prices(symbols: list[str], timeout: int = 20) -> dict[str, float]:
    session = cf_requests.Session(impersonate="chrome124")
    resp = session.get(
        _SPARK_URL,
        headers=_HEADERS,
        params={
            "symbols": ",".join(symbols),
            "range": "1d",
            "interval": "5m",
            "includePrePost": "false",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    out: dict[str, float] = {}
    for entry in resp.json().get("spark", {}).get("result", []) or []:
        symbol = entry.get("symbol") or ""
        responses = entry.get("response") or []
        if not symbol or not responses:
            continue
        meta = responses[0].get("meta") or {}
        price = meta.get("regularMarketPrice")
        if price is None:
            continue
        try:
            out[symbol] = float(price)
        except (TypeError, ValueError):
            continue
    return out


def build_market_compare() -> list[BenchmarkQuote]:
    symbols = [s for s, _ in _BENCHMARKS]
    try:
        prices = _fetch_prices(symbols)
    except Exception:
        prices = {}
    return [
        BenchmarkQuote(symbol=sym, name=name, price=prices.get(sym))
        for sym, name in _BENCHMARKS
    ]
