"""Buffett Indicator — total US equity market cap / GDP.

Scraped from gurufocus.com/economic_indicators/buffett-indicator which publishes
the ratio directly. Returns None for Gemini fallback if unavailable.
"""

from __future__ import annotations

import re

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_URL = "https://www.gurufocus.com/economic_indicators/buffett-indicator"
_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.gurufocus.com/",
}


class BuffettIndicatorResult(BaseModel):
    ratio_pct: float     # total market cap / GDP as percentage
    date: str
    source: str = "gurufocus.com Buffett Indicator"


class BuffettIndicatorNode(ScrapingNode):
    def scrape(self) -> BuffettIndicatorResult | None:
        return scrape_buffett_indicator()


def scrape_buffett_indicator() -> BuffettIndicatorResult | None:
    try:
        session = cf_requests.Session(impersonate="chrome124")
        resp = session.get(_URL, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        # Look for the ratio value in the page — pattern like "196.5%" or "Current: 196%"
        match = re.search(
            r'(?:Buffett Indicator|Current Ratio)[^\d]*?([\d]+\.?[\d]*)%',
            resp.text, re.IGNORECASE
        )
        if not match:
            # Try extracting from JSON-LD or script tags
            match = re.search(r'"ratio"\s*:\s*([\d]+\.?[\d]*)', resp.text)
        if not match:
            return None
        ratio = float(match.group(1))
        from datetime import date
        return BuffettIndicatorResult(ratio_pct=ratio, date=date.today().isoformat())
    except Exception:
        return None
