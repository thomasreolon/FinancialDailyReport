"""TIPS real yields — FRED DFII5 (5Y) and DFII10 (10Y)."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest


class RealYieldsResult(BaseModel):
    real_5y: float
    date_5y: str
    real_10y: float
    date_10y: str
    source: str = "FRED DFII5/DFII10"


class RealYieldsNode(ScrapingNode):
    def scrape(self) -> RealYieldsResult | None:
        return scrape_real_yields()


def scrape_real_yields() -> RealYieldsResult:
    d5, v5 = get_latest("DFII5")
    d10, v10 = get_latest("DFII10")
    return RealYieldsResult(
        real_5y=round(v5, 3),
        date_5y=d5.isoformat(),
        real_10y=round(v10, 3),
        date_10y=d10.isoformat(),
    )
