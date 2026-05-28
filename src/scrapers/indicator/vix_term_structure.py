"""VIX term structure — VIX3M (3-month) vs VIX (1-month) from Yahoo Finance.

Ratio < 1 (VIX3M < VIX): near-term panic, inverted term structure.
Ratio > 1: normal contango, market is calm short-term.
Rising ratio toward 1.20+ signals complacency; dip below 0.90 = fear spike.
"""

from __future__ import annotations

from datetime import datetime, timezone

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_HEADERS = {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}


class VixTermStructureResult(BaseModel):
    vix3m: float
    vix3m_date: str
    vix_spot: float
    vix_spot_date: str
    ratio: float           # VIX3M / VIX spot
    source: str = "Yahoo Finance ^VIX3M / ^VIX"


class VixTermStructureNode(ScrapingNode):
    def scrape(self) -> VixTermStructureResult | None:
        return scrape_vix_term_structure()


def _fetch_yahoo(symbol: str, session: cf_requests.Session) -> tuple[float, str]:
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    resp = session.get(url, params={"interval": "1d", "range": "5d"}, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice") or meta.get("previousClose")
    ts = meta.get("regularMarketTime")
    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else ""
    return round(float(price), 2), date_str


def scrape_vix_term_structure() -> VixTermStructureResult:
    session = cf_requests.Session(impersonate="chrome124")
    vix3m, d3m = _fetch_yahoo("%5EVIX3M", session)
    vix, dvix = _fetch_yahoo("%5EVIX", session)
    ratio = round(vix3m / vix, 3) if vix else None
    return VixTermStructureResult(
        vix3m=vix3m,
        vix3m_date=d3m,
        vix_spot=vix,
        vix_spot_date=dvix,
        ratio=ratio,
    )
