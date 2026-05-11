"""S&P 500 Shiller CAPE ratio — multpl.com/shiller-pe."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_URL = "https://www.multpl.com/shiller-pe"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class ShillerCapeResult(BaseModel):
    value: float
    date: str
    source: str = "multpl.com/shiller-pe"


class ShillerCapeNode(ScrapingNode):
    def scrape(self) -> ShillerCapeResult | None:
        return scrape_shiller_cape()


def scrape_shiller_cape() -> ShillerCapeResult:
    resp = requests.get(_URL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # The current value is in <div id="current"> or similar; also in <h2> with class "current"
    current_div = soup.find("div", id="current")
    if current_div:
        text = current_div.get_text(strip=True)
    else:
        # Fallback: find any element containing "Current"
        tag = soup.find(string=re.compile(r"Current", re.I))
        parent = tag.parent if tag else None
        text = parent.get_text(strip=True) if parent else ""

    match = re.search(r"[\d]+\.?[\d]*", text)
    if not match:
        raise ValueError(f"Could not parse CAPE value from: {text!r}")
    value = float(match.group())

    # Date is typically below the current value
    date_tag = soup.find("div", id="current-date") or soup.find("span", class_="current-date")
    date_str = date_tag.get_text(strip=True) if date_tag else ""
    return ShillerCapeResult(value=value, date=date_str)
