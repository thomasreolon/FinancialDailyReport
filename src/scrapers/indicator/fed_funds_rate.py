"""Effective fed funds rate — FRED DFF (daily)."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "DFF"


class FedFundsResult(BaseModel):
    rate_pct: float
    date: str
    source: str = "FRED DFF"


class FedFundsNode(ScrapingNode):
    def scrape(self) -> FedFundsResult | None:
        return scrape_fed_funds_rate()


def scrape_fed_funds_rate() -> FedFundsResult:
    d, val = get_latest(_SERIES)
    return FedFundsResult(rate_pct=round(val, 4), date=d.isoformat())
