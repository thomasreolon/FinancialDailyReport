"""CBOE VIX index — Yahoo Finance chart API."""

from __future__ import annotations

from datetime import datetime, timezone

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_URL = "https://query2.finance.yahoo.com/v8/finance/chart/%5EVIX"
_HEADERS = {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}


class VixResult(BaseModel):
    value: float
    date: str
    source: str = "Yahoo Finance ^VIX"


class VixNode(ScrapingNode):
    def scrape(self) -> VixResult | None:
        return scrape_vix()


def scrape_vix() -> VixResult:
    session = cf_requests.Session(impersonate="chrome124")
    resp = session.get(_URL, params={"interval": "1d", "range": "5d"}, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice") or meta.get("previousClose")
    ts = meta.get("regularMarketTime")
    dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else ""
    return VixResult(value=round(float(price), 2), date=dt_str)
