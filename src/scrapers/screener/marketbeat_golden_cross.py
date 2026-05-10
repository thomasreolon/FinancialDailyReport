"""
MarketBeat golden cross stocks screener.

Server-rendered HTML table. MarketBeat uses data-clean="SYMBOL|Company"
and data-sort-value="N" attributes on <td> cells for machine-readable values.
curl_cffi chrome124 bypasses Cloudflare TLS fingerprint check.
"""

import re

from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.api.web_fetcher import fetch_html
from src.scrapers.base import ScrapingNode

_URL = "https://www.marketbeat.com/stocks/golden-cross-stocks/"


class GoldenCrossStock(BaseModel):
    symbol: str
    company: str | None
    price: str | None
    golden_cross_date: str | None
    ma_50: str | None
    ma_200: str | None
    volume: str | None
    market_cap: str | None


class GoldenCrossResult(BaseModel):
    stocks: list[GoldenCrossStock]
    total: int


class GoldenCrossNode(ScrapingNode):
    def scrape(self) -> GoldenCrossResult | None:
        return scrape_golden_cross()


def scrape_golden_cross(timeout: int = 30) -> GoldenCrossResult:
    html = fetch_html(_URL, timeout=timeout)
    stocks = _parse(html)
    return GoldenCrossResult(stocks=stocks, total=len(stocks))


def _parse(html: str) -> list[GoldenCrossStock]:
    soup = BeautifulSoup(html, "html.parser")
    stocks: list[GoldenCrossStock] = []

    # Find the screener table
    table = None
    for tbl in soup.find_all("table"):
        headers = " ".join(th.get_text(strip=True).lower() for th in tbl.find_all("th"))
        if any(kw in headers for kw in ("symbol", "ticker", "company", "golden", "cross")):
            table = tbl
            break
    if table is None and soup.find_all("table"):
        table = max(soup.find_all("table"), key=lambda t: len(t.find_all("tr")))
    if table is None:
        return []

    # Build column map from headers
    col_map: list[str | None] = []
    thead = table.find("thead")
    if thead:
        for th in thead.find_all(["th", "td"]):
            txt = th.get_text(strip=True).lower()
            if "symbol" in txt or "ticker" in txt:
                col_map.append("symbol")
            elif "company" in txt or "name" in txt:
                col_map.append("company")
            elif "price" in txt and "target" not in txt:
                col_map.append("price")
            elif "golden" in txt or "cross" in txt or ("date" in txt and "ex" not in txt):
                col_map.append("golden_cross_date")
            elif "50" in txt:
                col_map.append("ma_50")
            elif "200" in txt:
                col_map.append("ma_200")
            elif "volume" in txt or "vol" in txt:
                col_map.append("volume")
            elif "cap" in txt:
                col_map.append("market_cap")
            else:
                col_map.append(None)
    else:
        col_map = ["symbol", "company", "price", "golden_cross_date", "ma_50", "ma_200", "volume", "market_cap"]

    tbody = table.find("tbody") or table
    for row in tbody.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or cells[0].name == "th":
            continue

        row_data: dict[str, str | None] = {
            "symbol": None, "company": None, "price": None,
            "golden_cross_date": None, "ma_50": None, "ma_200": None,
            "volume": None, "market_cap": None,
        }

        for i, cell in enumerate(cells):
            field = col_map[i] if i < len(col_map) else None

            # MarketBeat encodes "SYMBOL|Company Name" in data-clean on any cell
            data_clean = cell.get("data-clean", "")
            if data_clean and "|" in data_clean:
                parts = data_clean.split("|")
                candidate_symbol = parts[0].strip()
                # Treat as symbol|company only when symbol looks like a ticker (short, uppercase)
                if candidate_symbol and candidate_symbol.isupper() and len(candidate_symbol) <= 6:
                    if not row_data["symbol"]:
                        row_data["symbol"] = candidate_symbol
                    if len(parts) > 1 and not row_data["company"]:
                        row_data["company"] = parts[1].strip()
                    continue

            if field is None:
                continue

            sort_val = cell.get("data-sort-value", "")
            text = sort_val or cell.get_text(separator=" ", strip=True)

            if field == "symbol":
                a = cell.find("a")
                text = a.get_text(strip=True) if a else text

            row_data[field] = text or None

        if row_data.get("symbol"):
            stocks.append(GoldenCrossStock(**row_data))

    return stocks
