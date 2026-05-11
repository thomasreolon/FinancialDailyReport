"""Top S&P 500 sectors by EPS growth — FactSet EarningsInsight.

Paywalled source; returns None for Gemini fallback.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode


class LeadingSectorsResult(BaseModel):
    sectors: list[dict]  # [{"sector": "...", "eps_growth_pct": ...}, ...]
    quarter: str
    date: str
    source: str = "FactSet EarningsInsight"


class LeadingSectorsNode(ScrapingNode):
    def scrape(self) -> LeadingSectorsResult | None:
        return scrape_leading_sectors()


def scrape_leading_sectors() -> LeadingSectorsResult | None:
    return None
