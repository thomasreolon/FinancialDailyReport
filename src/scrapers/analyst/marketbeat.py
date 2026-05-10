"""
MarketBeat analyst forecast scraper — consensus + individual ratings.

Server-rendered HTML; curl_cffi chrome124 needed to pass Cloudflare TLS check.
"subscribe" in nav is a false positive — page content is accessible.
URL pattern: /stocks/{EXCHANGE}/{TICKER}/forecast/
"""

import re

from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_BASE = "https://www.marketbeat.com"
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Upgrade-Insecure-Requests": "1",
}


class ConsensusRating(BaseModel):
    overall: str | None
    buy_count: int | None
    hold_count: int | None
    sell_count: int | None
    avg_price_target: str | None
    high_price_target: str | None
    low_price_target: str | None
    upside_pct: str | None


class AnalystRating(BaseModel):
    date: str | None
    firm: str | None
    analyst: str | None
    action: str | None
    rating: str | None
    price_target: str | None


class MarketBeatForecastResult(BaseModel):
    ticker: str
    exchange: str
    consensus: ConsensusRating
    analysts: list[AnalystRating]
    analyst_count: int


class MarketBeatForecastNode(ScrapingNode):
    def __init__(self, ticker: str = "AAPL", exchange: str = "NASDAQ"):
        self.ticker = ticker.upper()
        self.exchange = exchange.upper()

    def scrape(self) -> MarketBeatForecastResult | None:
        return scrape_marketbeat_forecast(self.ticker, self.exchange)


def scrape_marketbeat_forecast(
    ticker: str, exchange: str = "NASDAQ", timeout: int = 30
) -> MarketBeatForecastResult:
    ticker = ticker.upper()
    exchange = exchange.upper()
    url = f"{_BASE}/stocks/{exchange}/{ticker}/forecast/"
    resp = cf_requests.get(url, impersonate="chrome124", headers=_HEADERS,
                           timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    analysts = _parse_analyst_table(soup)
    return MarketBeatForecastResult(
        ticker=ticker,
        exchange=exchange,
        consensus=_parse_consensus(soup),
        analysts=analysts,
        analyst_count=len(analysts),
    )


def _parse_consensus(soup: BeautifulSoup) -> ConsensusRating:
    overall = None
    rating_title = soup.find(class_="rating-title")
    if rating_title:
        overall = rating_title.get_text(strip=True) or None
    if not overall:
        for el in soup.find_all(string=re.compile(
            r"(Strong|Moderate|Unanimous)?\s*(Buy|Sell|Hold)", re.I
        )):
            text = el.strip()
            parent_cls = " ".join(el.parent.get("class", [])) if el.parent else ""
            if "rating" in parent_cls and 1 < len(text) < 40:
                overall = text
                break

    buy_count = hold_count = sell_count = None
    for label, attr in [("buy", "buy_count"), ("hold", "hold_count"), ("sell", "sell_count")]:
        el = soup.find(class_=re.compile(label, re.I)) or soup.find(id=re.compile(label, re.I))
        if el:
            nums = re.findall(r"\d+", el.get_text())
            if nums:
                if label == "buy":
                    buy_count = int(nums[0])
                elif label == "hold":
                    hold_count = int(nums[0])
                else:
                    sell_count = int(nums[0])

    avg_pt = high_pt = low_pt = upside = None
    pt_el = soup.find(string=re.compile(r"Price Target", re.I))
    if pt_el and pt_el.parent:
        amounts = re.findall(r"\$[\d,]+(?:\.\d+)?", pt_el.parent.get_text())
        if amounts:
            avg_pt = amounts[0]
            if len(amounts) > 1:
                high_pt = amounts[1]
            if len(amounts) > 2:
                low_pt = amounts[2]

    upside_el = soup.find(string=re.compile(r"upside|downside", re.I))
    if upside_el and upside_el.parent:
        pcts = re.findall(r"[+-]?\d+\.?\d*\s*%", upside_el.parent.get_text())
        if pcts:
            upside = pcts[0]

    return ConsensusRating(
        overall=overall,
        buy_count=buy_count,
        hold_count=hold_count,
        sell_count=sell_count,
        avg_price_target=avg_pt,
        high_price_target=high_pt,
        low_price_target=low_pt,
        upside_pct=upside,
    )


_ANALYST_COL_MAP = {
    "date": "date",
    "brokerage": "firm", "firm": "firm", "research": "firm",
    "analyst": "analyst",
    "action": "action", "activity": "action",
    "rating": "rating", "consensus": "rating",
    "price target": "price_target", "target": "price_target",
    # upside/downside column is not mapped (skip)
}


def _parse_analyst_table(soup: BeautifulSoup) -> list[AnalystRating]:
    analyst_table = None
    for tbl in soup.find_all("table"):
        headers_text = " ".join(
            th.get_text(strip=True).lower() for th in tbl.find_all(["th", "td"])[:10]
        )
        if any(kw in headers_text for kw in ("firm", "target", "brokerage", "analyst", "action")):
            analyst_table = tbl
            break

    if analyst_table is None:
        container = soup.find(class_=re.compile(r"scrollable|analyst|ratings.table", re.I))
        if container:
            analyst_table = container.find("table")

    if analyst_table is None:
        return []

    col_fields: list[str | None] = []
    thead = analyst_table.find("thead")
    if thead:
        for th in thead.find_all(["th", "td"]):
            txt = th.get_text(strip=True).lower()
            field = None
            for k, v in _ANALYST_COL_MAP.items():
                # avoid matching "report date" or "upside/downside" columns as plain "date"
                if k == "date" and "report" in txt:
                    continue
                if k in txt:
                    field = v
                    break
            col_fields.append(field)
    if not col_fields:
        col_fields = ["date", "firm", "analyst", "action", "rating", "price_target"]

    ratings: list[AnalystRating] = []
    tbody = analyst_table.find("tbody") or analyst_table
    for row in tbody.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or cells[0].name == "th":
            continue
        row_data: dict[str, str | None] = {
            "date": None, "firm": None, "analyst": None,
            "action": None, "rating": None, "price_target": None,
        }
        for i, cell in enumerate(cells):
            if i < len(col_fields) and col_fields[i]:
                val = cell.get_text(separator=" ", strip=True) or None
                row_data[col_fields[i]] = val
        if any(v for v in row_data.values()):
            ratings.append(AnalystRating(**row_data))
    return ratings
