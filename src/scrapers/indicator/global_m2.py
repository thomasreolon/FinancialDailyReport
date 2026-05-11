"""Global M2 money supply estimate.

No reliable free machine-readable source exists; returns None for Gemini fallback.
Primary source is macromicro.me (JavaScript-heavy) or aggregated central bank data.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode


class GlobalM2Result(BaseModel):
    value_trn: float
    date: str
    source: str = "estimate"


class GlobalM2Node(ScrapingNode):
    def scrape(self) -> GlobalM2Result | None:
        return scrape_global_m2()


def scrape_global_m2() -> GlobalM2Result | None:
    return None
