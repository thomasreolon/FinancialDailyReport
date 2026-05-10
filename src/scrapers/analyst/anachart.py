"""
AnaChart analyst ratings scraper.

Analyst data is in the main HTML page as a flex-based table
with CSS classes like ana-table-flex-td-key-{field_name}.
WP REST API only returns general company description, not ratings.
curl_cffi chrome124; no Cloudflare challenge observed (WP Rocket CDN).
"""

import re

from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_BASE = "https://anachart.com"
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}


class AnalystRating(BaseModel):
    analyst: str | None
    firm: str | None
    rating: str | None
    rating_since: str | None
    price_target: str | None
    prev_price_target: str | None
    target_date: str | None
    success_targets: str | None
    performance_score: str | None


class AnaChartResult(BaseModel):
    ticker: str
    url: str
    ratings: list[AnalystRating]
    count: int


class AnaChartNode(ScrapingNode):
    def __init__(self, ticker: str = "aapl"):
        self.ticker = ticker.lower()

    def scrape(self) -> AnaChartResult | None:
        return scrape_anachart(self.ticker)


def scrape_anachart(ticker: str, timeout: int = 30) -> AnaChartResult:
    ticker_lower = ticker.lower()
    url = f"{_BASE}/ticker/{ticker_lower}/"
    resp = cf_requests.get(url, impersonate="chrome124", headers=_HEADERS,
                           timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    ratings = _parse(resp.text)
    return AnaChartResult(ticker=ticker.upper(), url=url, ratings=ratings, count=len(ratings))


def _parse(html: str) -> list[AnalystRating]:
    soup = BeautifulSoup(html, "html.parser")
    ratings: list[AnalystRating] = []

    all_rows = soup.find_all(class_="ana-table-flex-row")
    data_rows = [r for r in all_rows if "ana-table-flex-header" not in r.get("class", [])]

    for row in data_rows:
        def _cell(key: str) -> str | None:
            el = row.find(class_=f"ana-table-flex-td-key-{key}")
            return el.get_text(separator=" ", strip=True) or None if el else None

        name_firm = _cell("analyst_name")
        analyst = firm = None
        if name_firm:
            m = re.match(r"^(.*?)\s*\((.+)\)$", name_firm)
            if m:
                analyst, firm = m.group(1).strip(), m.group(2).strip()
            else:
                analyst = name_firm

        rec_raw = _cell("last_price_recommendation") or ""
        rating = rating_since = None
        rm = re.match(r"^(\w[\w\s]*?)\s+Since\s+(.+)$", rec_raw, re.I)
        if rm:
            rating, rating_since = rm.group(1).strip(), rm.group(2).strip()
        elif rec_raw:
            rating = rec_raw

        target_date_raw = _cell("last_price_target_date") or ""
        target_date = None
        tdm = re.search(r"\((.+?)\)", target_date_raw)
        if tdm:
            target_date = tdm.group(1).strip()

        ratings.append(AnalystRating(
            analyst=analyst,
            firm=firm,
            rating=rating,
            rating_since=rating_since,
            price_target=_cell("last_price_target"),
            prev_price_target=_cell("previous_price_target"),
            target_date=target_date,
            success_targets=_cell("success_targets"),
            performance_score=_cell("performance_score"),
        ))

    return ratings
