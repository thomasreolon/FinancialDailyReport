"""5-year TIPS breakeven inflation rate — FRED T5YIE."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "T5YIE"


class Breakeven5yResult(BaseModel):
    rate_pct: float
    date: str
    source: str = "FRED T5YIE"


class Breakeven5yNode(ScrapingNode):
    def scrape(self) -> Breakeven5yResult | None:
        return scrape_breakeven_5y()


def scrape_breakeven_5y() -> Breakeven5yResult:
    d, val = get_latest(_SERIES)
    return Breakeven5yResult(rate_pct=round(val, 3), date=d.isoformat())
