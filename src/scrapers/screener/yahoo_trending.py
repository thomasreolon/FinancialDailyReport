"""
Yahoo Finance trending stocks — two-step crumb flow.

Step 1: GET /v1/test/getcrumb (returns a session crumb, requires cookie from same session).
Step 2: GET /v1/finance/trending/US for symbols, then /v7/finance/quote with crumb for prices.
The crumb is tied to the session cookie set during step 1.
"""

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_BASE = "https://query1.finance.yahoo.com"
_CRUMB_URL = f"{_BASE}/v1/test/getcrumb"
_TRENDING_URL = f"{_BASE}/v1/finance/trending/US"
_QUOTE_URL = f"{_BASE}/v7/finance/quote"
_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
}


class TrendingQuote(BaseModel):
    symbol: str
    name: str | None
    price: float | None
    change: float | None
    change_pct: float | None
    volume: int | None
    market_cap: float | None


class TrendingResult(BaseModel):
    quotes: list[TrendingQuote]
    count: int


class YahooTrendingNode(ScrapingNode):
    def __init__(self, count: int = 25, region: str = "US"):
        self.count = count
        self.region = region

    def scrape(self) -> TrendingResult | None:
        return scrape_yahoo_trending(count=self.count, region=self.region)


def scrape_yahoo_trending(count: int = 25, region: str = "US") -> TrendingResult:
    session = cf_requests.Session(impersonate="chrome124")

    crumb = session.get(_CRUMB_URL, headers=_HEADERS, timeout=20).text.strip()

    trending_resp = session.get(
        _TRENDING_URL,
        headers=_HEADERS,
        params={"region": region, "lang": "en-US", "count": count},
        timeout=20,
    )
    trending_resp.raise_for_status()
    finance = trending_resp.json().get("finance", {})
    if finance.get("error"):
        raise RuntimeError(f"Yahoo trending error: {finance['error']}")
    results = finance.get("result", [])
    if not results:
        return TrendingResult(quotes=[], count=0)

    symbols = [q["symbol"] for q in results[0].get("quotes", []) if q.get("symbol")]
    if not symbols:
        return TrendingResult(quotes=[], count=0)

    quote_resp = session.get(
        _QUOTE_URL,
        headers={**_HEADERS, "Accept": "application/json"},
        params={"symbols": ",".join(symbols), "lang": "en-US", "region": region, "crumb": crumb},
        timeout=20,
    )
    quote_resp.raise_for_status()
    raw_quotes = quote_resp.json().get("quoteResponse", {}).get("result", [])

    quotes = [
        TrendingQuote(
            symbol=q.get("symbol", ""),
            name=q.get("shortName") or q.get("longName"),
            price=q.get("regularMarketPrice"),
            change=q.get("regularMarketChange"),
            change_pct=q.get("regularMarketChangePercent"),
            volume=q.get("regularMarketVolume"),
            market_cap=q.get("marketCap"),
        )
        for q in raw_quotes
    ]
    return TrendingResult(quotes=quotes, count=len(quotes))
