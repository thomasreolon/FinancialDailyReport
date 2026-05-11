"""EuroStoxx 50 forward EPS growth estimate.

No freely accessible machine-readable source; returns None for Gemini fallback.
Authoritative sources: marketscreener.com (paywalled), JPM/Rothschild research.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode


class EuroStoxx50FwdEpsResult(BaseModel):
    growth_pct: float
    fiscal_year: str
    date: str
    source: str = "marketscreener.com"


class EuroStoxx50FwdEpsNode(ScrapingNode):
    def scrape(self) -> EuroStoxx50FwdEpsResult | None:
        return scrape_eurostoxx50_fwd_eps()


def scrape_eurostoxx50_fwd_eps() -> EuroStoxx50FwdEpsResult | None:
    return None
