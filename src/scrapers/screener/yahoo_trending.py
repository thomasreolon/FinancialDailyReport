"""
Yahoo Finance trending stocks — unofficial API endpoint.

Uses query1.finance.yahoo.com/v1/finance/trending/US which bypasses
the GDPR consent wall that blocks direct page access from EU IPs.
"""

from pydantic import BaseModel

from curl_cffi import requests as cf_requests
from src.scrapers.base import ScrapingNode

_API_URL = "https://query1.finance.yahoo.com/v1/finance/trending/US"
_API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://finance.yahoo.com",
    "Referer": "https://finance.yahoo.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
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
    resp = cf_requests.get(
        _API_URL,
        impersonate="chrome124",
        headers=_API_HEADERS,
        params={"region": region, "lang": "en-US", "count": count},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    finance = data.get("finance", {})
    if finance.get("error"):
        raise RuntimeError(f"Yahoo Finance API error: {finance['error']}")

    results = finance.get("result", [])
    if not results:
        return TrendingResult(quotes=[], count=0)

    quotes_raw = results[0].get("quotes", [])
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
        for q in quotes_raw
    ]
    return TrendingResult(quotes=quotes, count=len(quotes))
