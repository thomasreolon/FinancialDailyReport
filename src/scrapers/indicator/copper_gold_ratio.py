"""Copper/gold ratio — HG=F (copper $/lb) divided by GC=F (gold $/oz) from Yahoo Finance."""

from __future__ import annotations

from datetime import datetime, timezone

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_HEADERS = {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}


def _get_price(session: cf_requests.Session, symbol: str) -> tuple[float, str]:
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    resp = session.get(url, params={"interval": "1d", "range": "5d"}, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    price = float(meta.get("regularMarketPrice") or meta.get("previousClose"))
    ts = meta.get("regularMarketTime")
    dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else ""
    return price, dt_str


class CopperGoldRatioResult(BaseModel):
    ratio: float          # copper ($/lb) / gold ($/oz)
    copper_price: float   # $/lb
    gold_price: float     # $/oz
    date: str
    source: str = "Yahoo Finance HG=F / GC=F"


class CopperGoldRatioNode(ScrapingNode):
    def scrape(self) -> CopperGoldRatioResult | None:
        return scrape_copper_gold_ratio()


def scrape_copper_gold_ratio() -> CopperGoldRatioResult:
    session = cf_requests.Session(impersonate="chrome124")
    copper_price, date_str = _get_price(session, "HG%3DF")
    gold_price, _ = _get_price(session, "GC%3DF")
    ratio = round(copper_price / gold_price, 6)
    return CopperGoldRatioResult(
        ratio=ratio,
        copper_price=round(copper_price, 4),
        gold_price=round(gold_price, 2),
        date=date_str,
    )
