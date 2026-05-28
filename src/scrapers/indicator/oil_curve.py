"""WTI crude oil futures term structure — contango vs backwardation.

Fetches front-month (CL=F) and the contract ~12 months forward from Yahoo Finance.
wti_contango_pct > 0: contango (oversupply, bearish commodity signal)
wti_contango_pct < 0: backwardation (tight supply, bullish commodity signal)
The regime shift between the two is more predictive than the price level.
"""

from __future__ import annotations

from datetime import datetime, timezone, date

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_HEADERS = {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}

# Crude oil futures month codes
_MONTH_CODES = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
                7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}


class OilCurveResult(BaseModel):
    front_month_price: float
    front_month_ticker: str
    fwd_12m_price: float
    fwd_12m_ticker: str
    contango_pct: float        # (fwd - front) / front * 100
    date: str
    source: str = "Yahoo Finance CL futures"


class OilCurveNode(ScrapingNode):
    def scrape(self) -> OilCurveResult | None:
        return scrape_oil_curve()


def _forward_ticker(months_ahead: int = 12) -> str:
    today = date.today()
    target_month = today.month + months_ahead
    target_year = today.year + (target_month - 1) // 12
    target_month = ((target_month - 1) % 12) + 1
    code = _MONTH_CODES[target_month]
    return f"CL{code}{str(target_year)[-2:]}.NYM"


def _fetch_price(symbol: str, session: cf_requests.Session) -> tuple[float, str] | None:
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
        resp = session.get(url, params={"interval": "1d", "range": "5d"}, headers=_HEADERS, timeout=20)
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
        return round(float(price), 2), date_str
    except Exception:
        return None


def scrape_oil_curve() -> OilCurveResult:
    session = cf_requests.Session(impersonate="chrome124")

    front = _fetch_price("CL%3DF", session)
    if not front:
        raise RuntimeError("Oil curve: could not fetch front month (CL=F)")

    fwd_ticker = _forward_ticker(12)
    fwd = _fetch_price(fwd_ticker, session)
    if not fwd:
        # Try 11 months as fallback
        fwd_ticker = _forward_ticker(11)
        fwd = _fetch_price(fwd_ticker, session)
    if not fwd:
        raise RuntimeError(f"Oil curve: could not fetch 12M forward ({fwd_ticker})")

    front_price, front_date = front
    fwd_price, _ = fwd
    contango = round((fwd_price - front_price) / front_price * 100, 2)

    return OilCurveResult(
        front_month_price=front_price,
        front_month_ticker="CL=F",
        fwd_12m_price=fwd_price,
        fwd_12m_ticker=fwd_ticker,
        contango_pct=contango,
        date=front_date,
    )
