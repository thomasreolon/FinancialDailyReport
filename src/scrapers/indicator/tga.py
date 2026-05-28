"""Treasury General Account balance — FRED WTREGEN (weekly, $millions → $billions)."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "WTREGEN"


class TGAResult(BaseModel):
    value_bln: float
    date: str
    source: str = "FRED WTREGEN"


class TGANode(ScrapingNode):
    def scrape(self) -> TGAResult | None:
        return scrape_tga()


def scrape_tga() -> TGAResult:
    d, val = get_latest(_SERIES)
    return TGAResult(value_bln=round(val / 1_000, 1), date=d.isoformat())
