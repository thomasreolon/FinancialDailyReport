"""Core PCE price index YoY — FRED PCEPILFE."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_yoy

_SERIES = "PCEPILFE"


class CorePceResult(BaseModel):
    yoy_pct: float | None
    index_value: float
    date: str
    source: str = "FRED PCEPILFE"


class CorePceNode(ScrapingNode):
    def scrape(self) -> CorePceResult | None:
        return scrape_core_pce()


def scrape_core_pce() -> CorePceResult:
    d, val, yoy = get_yoy(_SERIES)
    return CorePceResult(yoy_pct=yoy, index_value=round(val, 3), date=d.isoformat())
