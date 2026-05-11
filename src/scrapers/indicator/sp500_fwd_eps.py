"""S&P 500 forward EPS consensus estimate.

FactSet EarningsInsight is the primary source but requires login.
Returns None for Gemini fallback.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode


class Sp500FwdEpsResult(BaseModel):
    fwd_eps: float
    fiscal_year: str
    date: str
    source: str = "FactSet EarningsInsight"


class Sp500FwdEpsNode(ScrapingNode):
    def scrape(self) -> Sp500FwdEpsResult | None:
        return scrape_sp500_fwd_eps()


def scrape_sp500_fwd_eps() -> Sp500FwdEpsResult | None:
    return None
