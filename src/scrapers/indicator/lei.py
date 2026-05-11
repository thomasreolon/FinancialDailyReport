"""Conference Board US Leading Economic Index — FRED USALOLITOAASTSAM (OECD CLI).

The Conference Board LEI (FRED USSLIND) was discontinued in 2020.
We use OECD's Composite Leading Indicator for the US instead (monthly, amplitude-adjusted).
Returns None for Gemini fallback if unavailable.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_mom

# OECD CLI for USA — monthly, available on FRED
_SERIES = "USALOLITOAASTSAM"


class LeiResult(BaseModel):
    value: float
    mom_pct: float | None
    date: str
    source: str = "FRED USALOLITOAASTSAM (OECD CLI USA)"


class LeiNode(ScrapingNode):
    def scrape(self) -> LeiResult | None:
        return scrape_lei()


def scrape_lei() -> LeiResult | None:
    try:
        d, val, mom = get_mom(_SERIES)
        return LeiResult(value=round(val, 3), mom_pct=mom, date=d.isoformat())
    except Exception:
        return None
