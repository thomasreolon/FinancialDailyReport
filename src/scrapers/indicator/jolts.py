"""JOLTS Quits Rate — FRED JTSQUR (monthly, %).

The quits rate is the share of workers who voluntarily left their jobs,
the best leading indicator of wage-push inflation pressure.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "JTSQUR"


class JOLTSResult(BaseModel):
    quits_rate_pct: float
    date: str
    source: str = "FRED JTSQUR"


class JOLTSNode(ScrapingNode):
    def scrape(self) -> JOLTSResult | None:
        return scrape_jolts()


def scrape_jolts() -> JOLTSResult:
    d, val = get_latest(_SERIES)
    return JOLTSResult(quits_rate_pct=round(val, 2), date=d.isoformat())
