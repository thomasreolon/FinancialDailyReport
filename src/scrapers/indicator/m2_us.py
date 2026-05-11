"""US M2 money supply — FRED M2SL, with YoY growth."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_yoy

_SERIES = "M2SL"


class M2UsResult(BaseModel):
    value_trn: float   # USD trillions
    yoy_pct: float | None
    date: str
    source: str = "FRED M2SL"


class M2UsNode(ScrapingNode):
    def scrape(self) -> M2UsResult | None:
        return scrape_m2_us()


def scrape_m2_us() -> M2UsResult:
    d, val, yoy = get_yoy(_SERIES)
    # M2SL is in billions of USD; convert to trillions
    value_trn = round(val / 1000, 3)
    return M2UsResult(value_trn=value_trn, yoy_pct=yoy, date=d.isoformat())
