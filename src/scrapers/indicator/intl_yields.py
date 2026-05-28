"""International 10Y government bond yields — German Bund and JGB.

Primary: FRED monthly series (reliable, ~1 month lag).
The US-Bund spread is the dominant driver of EUR/USD.
JGB yield moves signal BOJ policy shifts that can unwind the yen carry trade.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest, fetch_series

# Monthly series from ECB/OECD via FRED
_BUND_SERIES = "IRLTLT01DEM156N"
_JGB_SERIES  = "IRLTLT01JPM156N"
_US10Y_SERIES = "DGS10"


class IntlYieldsResult(BaseModel):
    bund_10y: float
    bund_date: str
    jgb_10y: float
    jgb_date: str
    us10y: float
    us10y_date: str
    us_bund_spread: float  # US10Y - Bund10Y
    source: str = "FRED IRLTLT01DEM156N / IRLTLT01JPM156N / DGS10"


class IntlYieldsNode(ScrapingNode):
    def scrape(self) -> IntlYieldsResult | None:
        return scrape_intl_yields()


def scrape_intl_yields() -> IntlYieldsResult:
    db, vb = get_latest(_BUND_SERIES)
    dj, vj = get_latest(_JGB_SERIES)
    du, vu = get_latest(_US10Y_SERIES)
    spread = round(vu - vb, 3)
    return IntlYieldsResult(
        bund_10y=round(vb, 3),
        bund_date=db.isoformat(),
        jgb_10y=round(vj, 3),
        jgb_date=dj.isoformat(),
        us10y=round(vu, 3),
        us10y_date=du.isoformat(),
        us_bund_spread=spread,
    )
