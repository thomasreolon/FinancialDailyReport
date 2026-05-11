"""10Y-3M Treasury yield spread — FRED T10Y3M."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "T10Y3M"


class YieldCurveResult(BaseModel):
    spread_pct: float
    date: str
    source: str = "FRED T10Y3M"


class YieldCurveNode(ScrapingNode):
    def scrape(self) -> YieldCurveResult | None:
        return scrape_yield_curve()


def scrape_yield_curve() -> YieldCurveResult:
    d, val = get_latest(_SERIES)
    return YieldCurveResult(spread_pct=round(val, 3), date=d.isoformat())
