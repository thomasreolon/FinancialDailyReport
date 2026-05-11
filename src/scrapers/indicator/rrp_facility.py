"""Fed overnight reverse repo (RRP) balance — FRED RRPONTSYD."""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SERIES = "RRPONTSYD"


class RrpFacilityResult(BaseModel):
    value_bln: float  # USD billions
    date: str
    source: str = "FRED RRPONTSYD"


class RrpFacilityNode(ScrapingNode):
    def scrape(self) -> RrpFacilityResult | None:
        return scrape_rrp_facility()


def scrape_rrp_facility() -> RrpFacilityResult:
    d, val = get_latest(_SERIES)
    # RRPONTSYD is in billions of USD
    return RrpFacilityResult(value_bln=round(val, 2), date=d.isoformat())
