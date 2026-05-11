"""S&P 500 blended EPS growth YoY for the latest quarter.

FactSet EarningsInsight is the authoritative source but is paywalled.
Returns None for Gemini fallback.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode


class Sp500EpsGrowthResult(BaseModel):
    growth_pct: float
    quarter: str   # e.g. "Q1 2025"
    date: str
    source: str = "FactSet EarningsInsight"


class Sp500EpsGrowthNode(ScrapingNode):
    def scrape(self) -> Sp500EpsGrowthResult | None:
        return scrape_sp500_eps_growth()


def scrape_sp500_eps_growth() -> Sp500EpsGrowthResult | None:
    return None
