"""Fed total assets (balance sheet) — FRED WALCL, weekly H.4.1."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "WALCL"


class FedBalanceSheetResult(BaseModel):
    value_trn: float  # USD trillions
    date: str
    source: str = "FRED WALCL"


class FedBalanceSheetNode(ScrapingNode):
    def scrape(self) -> FedBalanceSheetResult | None:
        return scrape_fed_balance_sheet()


def scrape_fed_balance_sheet() -> FedBalanceSheetResult:
    d, val = get_latest(_SERIES)
    # WALCL is in millions of USD; convert to trillions
    value_trn = round(val / 1_000_000, 3)
    return FedBalanceSheetResult(value_trn=value_trn, date=d.isoformat())
