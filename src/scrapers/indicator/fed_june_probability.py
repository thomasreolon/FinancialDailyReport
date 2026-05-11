"""CME FedWatch implied probability for next FOMC meeting.

CME FedWatch is JavaScript-heavy; returns None so the pipeline Gemini fallback handles it.
"""

from __future__ import annotations

from pydantic import BaseModel

from src.scrapers.base import ScrapingNode


class FedProbabilityResult(BaseModel):
    meeting_date: str
    hold_pct: float | None
    cut_25bp_pct: float | None
    cut_50bp_pct: float | None
    hike_25bp_pct: float | None
    source: str = "CME FedWatch"


class FedProbabilityNode(ScrapingNode):
    def scrape(self) -> FedProbabilityResult | None:
        return scrape_fed_june_probability()


def scrape_fed_june_probability() -> FedProbabilityResult | None:
    # CME FedWatch requires JavaScript rendering; returning None for Gemini fallback.
    return None
