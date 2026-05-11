"""CNN Fear & Greed Index — unofficial JSON endpoint."""

from __future__ import annotations

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {"Referer": "https://www.cnn.com/markets/fear-and-greed"}


class FearGreedResult(BaseModel):
    score: float
    rating: str  # e.g. "Fear", "Greed", "Extreme Fear"
    date: str
    source: str = "CNN Fear & Greed"


class FearGreedNode(ScrapingNode):
    def scrape(self) -> FearGreedResult | None:
        return scrape_fear_greed()


def scrape_fear_greed() -> FearGreedResult:
    session = cf_requests.Session(impersonate="chrome124")
    resp = session.get(_URL, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    fg = resp.json()["fear_and_greed"]
    score = float(fg["score"])
    rating = str(fg.get("rating", "")).capitalize()
    # timestamp is an ISO datetime string, e.g. "2026-05-08T23:59:55+00:00"
    timestamp = fg.get("timestamp", "")
    date_str = timestamp[:10] if timestamp else ""
    return FearGreedResult(score=round(score, 1), rating=rating, date=date_str)
