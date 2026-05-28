"""5-year/5-year forward inflation breakeven — FRED T5YIFR."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "T5YIFR"


class Breakeven5y5yResult(BaseModel):
    rate_pct: float
    date: str
    source: str = "FRED T5YIFR"


class Breakeven5y5yNode(ScrapingNode):
    def scrape(self) -> Breakeven5y5yResult | None:
        return scrape_breakeven_5y5y()


def scrape_breakeven_5y5y() -> Breakeven5y5yResult:
    d, val = get_latest(_SERIES)
    return Breakeven5y5yResult(rate_pct=round(val, 3), date=d.isoformat())
