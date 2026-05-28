"""Extended credit spreads — IG OAS and CCC OAS from FRED.

BAMLC0A0CM  = ICE BofA US Corporate (Investment Grade) OAS
BAMLH0A3HYM2 = ICE BofA CCC & Lower US High Yield OAS

Combined with the existing HY spread (BAMLH0A0HYM2) these form the full
credit quality stack: IG → HY → CCC.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest


class CreditSpreadsExtResult(BaseModel):
    ig_spread: float
    ig_date: str
    ccc_spread: float | None = None
    ccc_date: str | None = None
    source: str = "FRED BAMLC0A0CM / BAMLH0A3HYM2"


class CreditSpreadsExtNode(ScrapingNode):
    def scrape(self) -> CreditSpreadsExtResult | None:
        return scrape_credit_spreads_ext()


def scrape_credit_spreads_ext() -> CreditSpreadsExtResult:
    dig, vig = get_latest("BAMLC0A0CM")
    try:
        dccc, vccc = get_latest("BAMLH0A3HYM2")
        ccc_spread = round(vccc, 3)
        ccc_date = dccc.isoformat()
    except Exception:
        # CCC series requires FRED API key; works in production, may fail locally
        ccc_spread = None
        ccc_date = None
    return CreditSpreadsExtResult(
        ig_spread=round(vig, 3),
        ig_date=dig.isoformat(),
        ccc_spread=ccc_spread,
        ccc_date=ccc_date,
    )
