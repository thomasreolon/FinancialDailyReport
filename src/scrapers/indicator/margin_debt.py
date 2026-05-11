"""FINRA margin debt — scraped from FINRA margin statistics page."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_URL = "https://www.finra.org/investors/learn-to-invest/advanced-investing/margin-statistics"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class MarginDebtResult(BaseModel):
    value_bln: float   # USD billions (debit balances in margin accounts)
    date: str          # month/year of latest data
    source: str = "FINRA Margin Statistics"


class MarginDebtNode(ScrapingNode):
    def scrape(self) -> MarginDebtResult | None:
        return scrape_margin_debt()


def scrape_margin_debt() -> MarginDebtResult | None:
    try:
        resp = requests.get(_URL, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # FINRA renders margin stats in a table; grab the most recent row
        table = soup.find("table")
        if not table:
            return None
        rows = table.find_all("tr")
        # Find the last data row with a debit balance value
        for row in reversed(rows):
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            # Expect: Month, Debit Balances ($mil), Credit Balances ($mil), ...
            raw_date = cells[0]
            raw_debit = cells[1] if len(cells) > 1 else ""
            # Strip commas and parse
            debit_str = re.sub(r"[^\d.]", "", raw_debit)
            if not debit_str:
                continue
            debit_mil = float(debit_str)
            return MarginDebtResult(value_bln=round(debit_mil / 1000, 3), date=raw_date)
    except Exception:
        return None
