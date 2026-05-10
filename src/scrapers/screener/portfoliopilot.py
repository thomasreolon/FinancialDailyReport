"""
PortfolioPilot stock screener — Next.js App Router RSC streaming.

The stock data is embedded as JSON within self.__next_f RSC chunks.
Direct regex on the HTML is more reliable than full RSC parsing.
"""

import json
import re

from pydantic import BaseModel

from src.api.web_fetcher import fetch_html
from src.scrapers.base import ScrapingNode

_BASE = "https://portfoliopilot.com"
_SCREENER_URL = f"{_BASE}/explore/stock-screener/{{slug}}"


class ScreenerStock(BaseModel):
    ticker: str
    name: str | None = None
    price: float | None = None
    expected_return: float | None = None
    expected_risk: float | None = None
    expected_sharpe: float | None = None
    beta: float | None = None
    correl_to_market: float | None = None
    market_cap: float | None = None
    pe_ratio: float | None = None
    recommendation: str | None = None


class PortfolioPilotResult(BaseModel):
    screener_slug: str
    stocks: list[ScreenerStock]


class PortfolioPilotNode(ScrapingNode):
    def __init__(self, slug: str = "motley-fool-top-10-stocks"):
        self.slug = slug

    def scrape(self) -> PortfolioPilotResult | None:
        return scrape_portfoliopilot(self.slug)


def scrape_portfoliopilot(slug: str = "motley-fool-top-10-stocks") -> PortfolioPilotResult:
    url = _SCREENER_URL.format(slug=slug)
    html = fetch_html(url, timeout=30)
    stocks = _parse_stocks(html)
    return PortfolioPilotResult(screener_slug=slug, stocks=stocks)


def _safe_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _parse_stocks(html: str) -> list[ScreenerStock]:
    # RSC chunks encode JSON with backslash-escaped quotes: \"stocks\":[{\"ticker\":...}]
    # Decode to plain JSON then parse.
    stocks_by_ticker: dict[str, ScreenerStock] = {}

    # Locate escaped stocks array and decode it
    escaped_marker = '\\"stocks\\"'
    idx = html.find(escaped_marker)
    if idx != -1:
        # Walk back to find the opening { of the containing object
        obj_start = html.rfind("{", 0, idx)
        if obj_start != -1:
            # Extract a generous chunk and decode escaped quotes
            chunk = html[obj_start:obj_start + 50_000]
            decoded = chunk.replace('\\"', '"').replace("\\\\", "\\")
            m = re.search(r'"stocks"\s*:\s*(\[.*?\])\s*[,}]', decoded, re.S)
            if m:
                try:
                    arr = json.loads(m.group(1))
                    for item in arr:
                        _add_stock(item, stocks_by_ticker)
                except json.JSONDecodeError:
                    pass

    # Fallback: try unescaped pattern (in case site changes to plain JSON)
    if not stocks_by_ticker:
        m2 = re.search(r'"stocks"\s*:\s*(\[(?:\{[^}]*"ticker"[^}]*\}[,\s]*)+\])', html)
        if m2:
            try:
                arr = json.loads(m2.group(1))
                for item in arr:
                    _add_stock(item, stocks_by_ticker)
            except json.JSONDecodeError:
                pass

    return list(stocks_by_ticker.values())


def _add_stock(obj: dict, stocks: dict[str, "ScreenerStock"]) -> None:
    ticker = obj.get("ticker")
    if not isinstance(ticker, str) or not ticker:
        return
    ticker = ticker.upper()
    if ticker in stocks:
        return
    stocks[ticker] = ScreenerStock(
        ticker=ticker,
        name=obj.get("name") or obj.get("companyName"),
        price=_safe_float(obj.get("price") or obj.get("lastPrice")),
        expected_return=_safe_float(obj.get("expectedReturn")),
        expected_risk=_safe_float(obj.get("expectedRisk")),
        expected_sharpe=_safe_float(obj.get("expectedSharpe")),
        beta=_safe_float(obj.get("beta")),
        correl_to_market=_safe_float(obj.get("correlToMarket")),
        market_cap=_safe_float(obj.get("marketCap")),
        pe_ratio=_safe_float(obj.get("peRatio")),
        recommendation=obj.get("recommendation") or obj.get("rating"),
    )
