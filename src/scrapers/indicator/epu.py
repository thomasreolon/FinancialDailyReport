"""Economic Policy Uncertainty (EPU) Index — Baker, Bloom & Davis.

Downloaded from policyuncertainty.com CSV. US EPU spikes ahead of
investment slowdowns and regime changes. Monthly.
"""

from __future__ import annotations

import csv
import io

import requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_CSV_URL = "https://www.policyuncertainty.com/media/US_Policy_Uncertainty_Data.csv"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


class EPUResult(BaseModel):
    epu_index: float
    date: str          # YYYY-MM (monthly)
    source: str = "PolicyUncertainty.com US EPU"


class EPUNode(ScrapingNode):
    def scrape(self) -> EPUResult | None:
        return scrape_epu()


def scrape_epu() -> EPUResult:
    resp = requests.get(_CSV_URL, headers=_HEADERS, timeout=30)
    resp.raise_for_status()

    rows = list(csv.reader(io.StringIO(resp.text)))
    if not rows:
        raise ValueError("EPU: empty CSV")

    # Find the header row to locate the "Three_Component_Index" column
    # Columns: Year, Month, News_Based_Policy_Uncert_Index, ..., Three_Component_Index, ...
    header = rows[0]
    # Prefer the composite three-component index; fall back to News_Based
    for col_name in ("Three_Component_Index", "News_Based_Policy_Uncert_Index"):
        try:
            col_idx = next(i for i, h in enumerate(header) if col_name.lower() in h.lower().replace(" ", "_"))
            break
        except StopIteration:
            col_idx = None
    if col_idx is None:
        # last numeric column as fallback
        col_idx = len(header) - 1

    # Find last non-empty row
    for row in reversed(rows[1:]):
        if len(row) <= col_idx:
            continue
        val_str = row[col_idx].strip()
        if not val_str:
            continue
        try:
            val = float(val_str)
            year = row[0].strip()
            month = row[1].strip().zfill(2)
            date_str = f"{year}-{month}"
            return EPUResult(epu_index=round(val, 1), date=date_str)
        except (ValueError, IndexError):
            continue

    raise ValueError("EPU: no valid data row found")
