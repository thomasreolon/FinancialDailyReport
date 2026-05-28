"""ICE BofA MOVE Index — bond market implied volatility.

Tries Yahoo Finance ^MOVE first; falls back to scraping TradingEconomics.
MOVE spikes precede credit events and Fed pivot moments.
Divergence: low VIX + high MOVE = rates uncertainty masking equity calm.
"""

from __future__ import annotations

from datetime import datetime, timezone

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.api.web_fetcher import fetch_html

_HEADERS = {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}
_TE_URL = "https://tradingeconomics.com/united-states/ice-bofa-move-index"


class MoveIndexResult(BaseModel):
    value: float
    date: str
    source: str


class MoveIndexNode(ScrapingNode):
    def scrape(self) -> MoveIndexResult | None:
        return scrape_move_index()


def _try_yahoo() -> MoveIndexResult | None:
    try:
        session = cf_requests.Session(impersonate="chrome124")
        resp = session.get(
            "https://query2.finance.yahoo.com/v8/finance/chart/%5EMOVE",
            params={"interval": "1d", "range": "5d"},
            headers=_HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()["chart"]["result"]
        if not result:
            return None
        meta = result[0]["meta"]
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        if not price:
            return None
        ts = meta.get("regularMarketTime")
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else ""
        return MoveIndexResult(value=round(float(price), 2), date=date_str, source="Yahoo Finance ^MOVE")
    except Exception:
        return None


def _try_tradingeconomics() -> MoveIndexResult | None:
    try:
        from bs4 import BeautifulSoup
        html = fetch_html(_TE_URL, timeout=30)
        soup = BeautifulSoup(html, "html.parser")
        # TradingEconomics displays current value in a <span id="ctl00_ContentPlaceHolder1_ctl00_lblIndexValue">
        for sel in ["#ctl00_ContentPlaceHolder1_ctl00_lblIndexValue", ".act-value"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True).replace(",", "")
                val = float(text)
                return MoveIndexResult(value=round(val, 2), date="", source="TradingEconomics")
    except Exception:
        pass
    return None


def scrape_move_index() -> MoveIndexResult:
    result = _try_yahoo()
    if result:
        return result
    result = _try_tradingeconomics()
    if result:
        return result
    raise RuntimeError("MOVE index: all fetch tiers failed")
