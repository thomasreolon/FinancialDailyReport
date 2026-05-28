"""AAII Investor Sentiment Survey — weekly bull/bear percentages.

Extreme bear readings (bear > 50%) are historically strong contrarian buy signals.
Bull-Bear spread below -30 has preceded major market bottoms.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.api.web_fetcher import fetch_html

_URL = "https://www.aaii.com/sentimentsurvey/sent_results"


class AAIISentimentResult(BaseModel):
    bull_pct: float
    neutral_pct: float
    bear_pct: float
    bull_bear_spread: float   # bull% - bear%
    date: str
    source: str = "AAII Sentiment Survey"


class AAIISentimentNode(ScrapingNode):
    def scrape(self) -> AAIISentimentResult | None:
        return scrape_aaii_sentiment()


def _parse_pct(text: str) -> float | None:
    text = text.strip().rstrip("%").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def scrape_aaii_sentiment() -> AAIISentimentResult:
    html = fetch_html(_URL, timeout=30)
    soup = BeautifulSoup(html, "html.parser")

    # The survey results are in a table; first data row is most recent week
    table = soup.find("table", {"id": "sentiment-data"}) or soup.find("table")
    if not table:
        raise RuntimeError("AAII: sentiment table not found")

    rows = table.find_all("tr")
    # Skip header rows, find first data row
    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        # Skip header rows
        if any(h in cells[0].lower() for h in ("date", "week", "period", "reported")):
            continue
        # Expect: Date, Bullish%, Neutral%, Bearish%
        date_str = cells[0]
        if not re.search(r"\d", date_str):  # must contain at least one digit
            continue
        bull = _parse_pct(cells[1])
        neutral = _parse_pct(cells[2])
        bear = _parse_pct(cells[3])
        if bull is None or bear is None:
            continue
        if neutral is None:
            neutral = round(100.0 - bull - bear, 1)
        spread = round(bull - bear, 1)
        return AAIISentimentResult(
            bull_pct=round(bull, 1),
            neutral_pct=round(neutral, 1),
            bear_pct=round(bear, 1),
            bull_bear_spread=spread,
            date=date_str,
        )

    raise RuntimeError("AAII: no data rows found in sentiment table")
