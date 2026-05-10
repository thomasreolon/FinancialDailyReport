"""
Investing.com sentiment-outlook scraper.

Source: https://it.investing.com/markets/sentiment-outlook

Extracts two data layers from the page:
  1. Sentiment table — per-asset bullish/bearish % split and position counts
  2. Embedded chart JSON — community long/short performance % vs absolute move
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.api.web_fetcher import fetch_html
from src.scrapers.base import ScrapingNode

_URL = "https://it.investing.com/markets/sentiment-outlook"

_IT_TO_EN: dict[str, str] = {
    "Oro": "Gold",
    "Bitcoin": "Bitcoin",
    "Petrolio Greggio": "Crude Oil (WTI)",
    "Petrolio Brent": "Brent Oil",
    "Argento": "Silver",
    "NVIDIA": "NVIDIA",
    "Nasdaq 100": "Nasdaq 100",
    "Gas naturale": "Natural Gas",
    "Micron": "Micron",
}


# ── models ────────────────────────────────────────────────────────────────────

class SentimentEntry(BaseModel):
    name: str
    name_en: str | None
    bullish_pct: int | None
    bearish_pct: int | None
    long_count: int | None
    short_count: int | None
    community_long_pct: float | None
    community_short_pct: float | None
    absolute_pct: float | None
    performance_date: str | None


class SentimentOutlookResult(BaseModel):
    entries: list[SentimentEntry]
    count: int
    fetched_at: str


# ── parsing ───────────────────────────────────────────────────────────────────

def _parse_sentiment_table(soup: BeautifulSoup) -> list[dict]:
    tbl = soup.find("table", class_="sentimentsOutlookTbl")
    if not tbl:
        return []

    rows = []
    for tr in tbl.find_all("tr"):
        cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(["td", "th"])]
        if not cells or cells[0] in ("Nome", ""):
            continue

        name = cells[0] if len(cells) > 0 else None
        sentiment_cell = cells[1] if len(cells) > 1 else ""

        bullish_pct = bearish_pct = None
        m = re.search(r"Rialzista\s+(\d+)%.*?Ribassista\s+(\d+)%", sentiment_cell)
        if m:
            bullish_pct = int(m.group(1))
            bearish_pct = int(m.group(2))

        long_count  = _to_int(cells[2]) if len(cells) > 2 else None
        short_count = _to_int(cells[3]) if len(cells) > 3 else None

        rows.append({
            "name": name,
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "long_count": long_count,
            "short_count": short_count,
        })
    return rows


def _parse_chart_series(html: str) -> tuple[list[dict], list[float]]:
    """Return (community_data_list, absolute_data_list) from embedded chart JSON."""
    idx = html.find('"series":[')
    if idx == -1:
        return [], []

    start = html.find("[", idx)
    depth = 0
    for i, ch in enumerate(html[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                series_raw = html[start : i + 1]
                break
    else:
        return [], []

    try:
        series = json.loads(series_raw)
    except json.JSONDecodeError:
        return [], []

    community = next((s["data"] for s in series if s.get("id") == "community"), [])
    absolute  = next((s["data"] for s in series if s.get("id") == "absolute"), [])
    return community, absolute


def _to_int(value: str) -> int | None:
    cleaned = re.sub(r"[^\d]", "", value)
    return int(cleaned) if cleaned else None


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ── public API ────────────────────────────────────────────────────────────────

class SentimentOutlookNode(ScrapingNode):
    def scrape(self) -> SentimentOutlookResult | None:
        return scrape_sentiment_outlook()


def scrape_sentiment_outlook(timeout: int = 30) -> SentimentOutlookResult:
    html = fetch_html(_URL, timeout=timeout)
    soup = BeautifulSoup(html, "html.parser")

    table_rows = _parse_sentiment_table(soup)
    community_data, absolute_data = _parse_chart_series(html)

    entries: list[SentimentEntry] = []
    for i, row in enumerate(table_rows):
        comm = community_data[i] if i < len(community_data) else {}
        abs_val = absolute_data[i] if i < len(absolute_data) else None

        name = row["name"] or ""
        entries.append(SentimentEntry(
            name=name,
            name_en=_IT_TO_EN.get(name),
            bullish_pct=row["bullish_pct"],
            bearish_pct=row["bearish_pct"],
            long_count=row["long_count"],
            short_count=row["short_count"],
            community_long_pct=_to_float(comm.get("long_value")),
            community_short_pct=_to_float(comm.get("short_value")),
            absolute_pct=_to_float(abs_val),
            performance_date=comm.get("performance_date"),
        ))

    return SentimentOutlookResult(
        entries=entries,
        count=len(entries),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
