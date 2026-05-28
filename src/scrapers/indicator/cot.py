"""CFTC Commitments of Traders (COT) — net speculator positioning.

Two CFTC reports are used:
- Traders in Financial Futures (TFF): S&P 500, 10Y Treasury, EUR, JPY, USD Index
  Leveraged Funds column (hedge funds / CTAs).
- Legacy Futures Only (deacot): Gold — Noncommercial (large speculators) column.

Net > 0: speculators are net long (bullish).
Net < 0: net short (bearish).
Extremes are contrarian signals; direction changes confirm trend reversals.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime

import requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_HEADERS: dict = {}  # CFTC blocks browser UAs; no User-Agent header works fine
_TFF_URL    = "https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
_LEGACY_URL = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"

# TFF contracts — Leveraged Funds positioning
_TFF_CONTRACTS = {
    "E-MINI S&P 500": "sp500",
    "UST 10Y NOTE":   "tnote_10y",
    "EURO FX":        "eur",
    "JAPANESE YEN":   "jpy",
    "USD INDEX":      "usd_index",
}

# Legacy contracts — Noncommercial (large speculator) positioning
_LEGACY_CONTRACTS = {
    "GOLD - COMMODITY EXCHANGE INC.": "gold",
}


class COTResult(BaseModel):
    sp500_net: int | None = None
    tnote_10y_net: int | None = None
    eur_net: int | None = None
    jpy_net: int | None = None
    usd_index_net: int | None = None
    gold_net: int | None = None
    report_date: str | None = None
    source: str = "CFTC TFF + Legacy Futures"


class COTNode(ScrapingNode):
    def scrape(self) -> COTResult | None:
        return scrape_cot()


def _download_rows(url_template: str, year: int) -> list[dict] | None:
    url = url_template.format(year=year)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=60)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            fname = zf.namelist()[0]
            with zf.open(fname) as f:
                text = f.read().decode("utf-8", errors="replace")
        return list(csv.DictReader(io.StringIO(text)))
    except Exception:
        return None


def _net_int(row: dict, long_col: str, short_col: str) -> int | None:
    try:
        l = int(row[long_col].replace(",", "").strip())
        s = int(row[short_col].replace(",", "").strip())
        return l - s
    except (KeyError, ValueError):
        return None


def _latest_per_contract(rows: list[dict], name_col: str, date_col: str,
                          contracts: dict[str, str]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in rows:
        name = row.get(name_col, "").upper()
        for key, field in contracts.items():
            if key.upper() in name:
                if latest.get(field) is None or row.get(date_col, "") > latest[field].get(date_col, ""):
                    latest[field] = row
                break
    return latest


def _parse_yymmdd(raw: str) -> str | None:
    try:
        return datetime.strptime(raw.strip(), "%y%m%d").date().isoformat()
    except ValueError:
        return raw or None


def scrape_cot() -> COTResult:
    year = datetime.now().year
    result = COTResult()

    # ── TFF: financial futures ─────────────────────────────────────────────────
    tff_rows = _download_rows(_TFF_URL, year) or _download_rows(_TFF_URL, year - 1)
    if tff_rows:
        latest = _latest_per_contract(
            tff_rows, "Market_and_Exchange_Names", "As_of_Date_In_Form_YYMMDD", _TFF_CONTRACTS
        )
        for field, row in latest.items():
            net = _net_int(row, "Lev_Money_Positions_Long_All", "Lev_Money_Positions_Short_All")
            setattr(result, f"{field}_net", net)
        dates = [r.get("As_of_Date_In_Form_YYMMDD", "") for r in latest.values()]
        if dates:
            result.report_date = _parse_yymmdd(max(set(dates), key=dates.count))

    # ── Legacy: commodity futures (Gold) ───────────────────────────────────────
    legacy_rows = _download_rows(_LEGACY_URL, year) or _download_rows(_LEGACY_URL, year - 1)
    if legacy_rows:
        latest = _latest_per_contract(
            legacy_rows, "Market and Exchange Names", "As of Date in Form YYMMDD", _LEGACY_CONTRACTS
        )
        for field, row in latest.items():
            net = _net_int(row, "Noncommercial Positions-Long (All)", "Noncommercial Positions-Short (All)")
            setattr(result, f"{field}_net", net)

    if tff_rows is None and legacy_rows is None:
        raise RuntimeError("COT: could not download any CFTC data")

    return result
