"""Equity risk premium — forward earnings yield minus 10Y real yield.

10Y real yield = DGS10 (nominal) - T10YIE (breakeven).
Forward earnings yield = 1 / forward P/E from Yahoo Finance S&P 500 quoteSummary.
Returns None if forward P/E is unavailable (indices don't always expose it).
"""

from __future__ import annotations

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_QUOTE_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/%5EGSPC"
_HEADERS = {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}


class EquityRiskPremiumResult(BaseModel):
    erp_pct: float | None          # forward earnings yield - real yield
    real_yield_10y: float | None
    forward_earnings_yield: float | None
    fwd_pe: float | None
    date: str
    source: str = "FRED DGS10/T10YIE + Yahoo Finance ^GSPC"


class EquityRiskPremiumNode(ScrapingNode):
    def scrape(self) -> EquityRiskPremiumResult | None:
        return scrape_equity_risk_premium()


def scrape_equity_risk_premium() -> EquityRiskPremiumResult:
    d_nom, nom_yield = get_latest("DGS10")
    d_be, breakeven = get_latest("T10YIE")
    real_yield = round(nom_yield - breakeven, 3)

    # Try to get forward P/E from Yahoo Finance
    fwd_pe: float | None = None
    try:
        session = cf_requests.Session(impersonate="chrome124")
        resp = session.get(
            _QUOTE_URL,
            params={"modules": "defaultKeyStatistics,summaryDetail"},
            headers=_HEADERS,
            timeout=20,
        )
        if resp.status_code == 200:
            result = resp.json().get("quoteSummary", {}).get("result") or []
            if result:
                ks = result[0].get("defaultKeyStatistics", {})
                raw = ks.get("forwardPE", {})
                if isinstance(raw, dict):
                    fwd_pe = raw.get("raw")
                elif isinstance(raw, (int, float)):
                    fwd_pe = float(raw)
    except Exception:
        pass

    fwd_earnings_yield: float | None = None
    erp: float | None = None
    if fwd_pe and fwd_pe > 0:
        fwd_earnings_yield = round(100 / fwd_pe, 3)
        erp = round(fwd_earnings_yield - real_yield, 3)

    return EquityRiskPremiumResult(
        erp_pct=erp,
        real_yield_10y=real_yield,
        forward_earnings_yield=fwd_earnings_yield,
        fwd_pe=round(fwd_pe, 2) if fwd_pe else None,
        date=max(d_nom, d_be).isoformat(),
    )
