"""S&P 500 forward 12-month P/E ratio.

FactSet EarningsInsight is the primary source but requires login.
Tries Yahoo Finance as a fallback (quoteSummary rarely exposes fwd PE for ^GSPC).
Returns None for Gemini fallback if unavailable.
"""

from __future__ import annotations

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/%5EGSPC"
_HEADERS = {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}


class Sp500FwdPeResult(BaseModel):
    fwd_pe: float
    date: str
    source: str = "Yahoo Finance ^GSPC"


class Sp500FwdPeNode(ScrapingNode):
    def scrape(self) -> Sp500FwdPeResult | None:
        return scrape_sp500_fwd_pe()


def scrape_sp500_fwd_pe() -> Sp500FwdPeResult | None:
    try:
        session = cf_requests.Session(impersonate="chrome124")
        resp = session.get(
            _URL,
            params={"modules": "defaultKeyStatistics,summaryDetail"},
            headers=_HEADERS,
            timeout=20,
        )
        if resp.status_code != 200:
            return None
        result = resp.json().get("quoteSummary", {}).get("result") or []
        if not result:
            return None
        ks = result[0].get("defaultKeyStatistics", {})
        raw = ks.get("forwardPE", {})
        fwd_pe: float | None = None
        if isinstance(raw, dict):
            fwd_pe = raw.get("raw")
        elif isinstance(raw, (int, float)):
            fwd_pe = float(raw)
        if not fwd_pe:
            return None
        from datetime import date
        return Sp500FwdPeResult(fwd_pe=round(fwd_pe, 2), date=date.today().isoformat())
    except Exception:
        return None
