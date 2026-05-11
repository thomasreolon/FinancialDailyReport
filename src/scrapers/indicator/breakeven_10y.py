"""10-year TIPS breakeven inflation rate — FRED T10YIE."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "T10YIE"


class Breakeven10yResult(BaseModel):
    rate_pct: float
    date: str
    source: str = "FRED T10YIE"


class Breakeven10yNode(ScrapingNode):
    def scrape(self) -> Breakeven10yResult | None:
        return scrape_breakeven_10y()


def scrape_breakeven_10y() -> Breakeven10yResult:
    d, val = get_latest(_SERIES)
    return Breakeven10yResult(rate_pct=round(val, 3), date=d.isoformat())
