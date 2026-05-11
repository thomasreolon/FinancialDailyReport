"""ISM Manufacturing PMI — macrotrends.net scrape.

FRED's NAPM series is no longer available. We scrape macrotrends for the latest reading.
Returns None for Gemini fallback if the page is unavailable.
"""

from __future__ import annotations

import json
import re

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_URL = "https://www.macrotrends.net/1375/ism-manufacturing-index-monthly"
_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.macrotrends.net/",
}


class IsmPmiResult(BaseModel):
    value: float   # PMI reading (>50 = expansion, <50 = contraction)
    date: str
    source: str = "macrotrends.net (ISM Manufacturing)"


class IsmPmiNode(ScrapingNode):
    def scrape(self) -> IsmPmiResult | None:
        return scrape_ism_pmi()


def scrape_ism_pmi() -> IsmPmiResult | None:
    try:
        session = cf_requests.Session(impersonate="chrome124")
        resp = session.get(_URL, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        # macrotrends embeds chart data as a JS variable: var chartData = {...}
        match = re.search(r'var\s+chartData\s*=\s*(\{.*?\});', resp.text, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(1))
        # chartData keys are date strings "YYYY-MM-DD", values are dicts with v1/v2
        dates = sorted(data.keys())
        if not dates:
            return None
        latest_date = dates[-1]
        val = data[latest_date].get("v1") or data[latest_date].get("v2")
        if val is None:
            return None
        return IsmPmiResult(value=round(float(val), 1), date=latest_date)
    except Exception:
        return None
