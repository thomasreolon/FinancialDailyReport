"""
Mid-cap US stocks sorted by worst daily % change — investing.com screener.

Uses the ssid URL parameter to trigger server-side filtered rendering.
The ssid encodes the filter (market cap range) and sort as base64 JSON.
"""

import base64
import json
import re

from pydantic import BaseModel

from src.api.web_fetcher import fetch_html
from src.scrapers.base import ScrapingNode

_SCREENER_URL = "https://www.investing.com/stock-screener"
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
_MID_CAP_LOW = 2_000_000_000
_MID_CAP_HIGH = 10_000_000_000


class ScreenerRow(BaseModel):
    ticker: str
    name: str
    exchange: str
    sector: str
    industry: str
    market_cap_usd: float | None
    market_cap_display: str
    price: float | None
    day_change_pct: float | None
    pe_ratio: float | None
    peg_ratio: float | None
    fair_value_label: str | None
    analyst_target: float | None
    analyst_target_upside: float | None
    fin_health_label: str | None
    path: str


class ScreenerResult(BaseModel):
    rows: list[ScreenerRow]
    total_in_universe: int


class MidCapLosersNode(ScrapingNode):
    def __init__(
        self,
        limit: int = 30,
        market: str = "US",
        mktcap_low: float = _MID_CAP_LOW,
        mktcap_high: float = _MID_CAP_HIGH,
    ):
        self.limit = limit
        self.market = market
        self.mktcap_low = mktcap_low
        self.mktcap_high = mktcap_high

    def scrape(self) -> ScreenerResult | None:
        return scrape_mid_cap_losers(
            limit=self.limit,
            market=self.market,
            mktcap_low=self.mktcap_low,
            mktcap_high=self.mktcap_high,
        )


def scrape_mid_cap_losers(
    limit: int = 30,
    market: str = "US",
    mktcap_low: float = _MID_CAP_LOW,
    mktcap_high: float = _MID_CAP_HIGH,
    timeout: int = 30,
) -> ScreenerResult:
    ssid = _make_ssid(market, mktcap_low, mktcap_high, page_size=min(limit, 30))
    url = f"{_SCREENER_URL}?ssid={ssid}"
    html = fetch_html(url, timeout=timeout)
    res = _extract_results(html)
    cols = [c["metric"] for c in res.get("columns", [])]
    rows = res.get("rows", [])
    total = res.get("page", {}).get("totalItems", 0)
    return ScreenerResult(
        rows=[_parse_row(r, cols) for r in rows[:limit]],
        total_in_universe=total,
    )


def _make_ssid(
    market: str,
    mktcap_low: float,
    mktcap_high: float,
    sort_metric: str = "asset_price_latest_change_pct",
    sort_dir: str = "ASC",
    page_size: int = 30,
) -> str:
    preset_obj = {
        "keys": [
            "currency", "gt.inclusive", "gt.scale", "gt.value",
            "lt.inclusive", "lt.scale", "lt.value", "metric",
        ],
        "values": ["USD", True, 1, mktcap_low, True, 1, mktcap_high, "marketcap_adj_latest"],
    }
    preset_hex = json.dumps(preset_obj, separators=(",", ":")).encode().hex()
    ssid_obj = {
        "keys": [
            "connective", "filters.0.metric", "filters.0.preset", "limit",
            "prefilters.market", "prefilters.primaryOnly", "sort.direction", "sort.metric",
        ],
        "values": ["ALL", "marketcap_adj_latest", preset_hex, page_size, market, False, sort_dir, sort_metric],
    }
    b64 = base64.b64encode(json.dumps(ssid_obj, separators=(",", ":")).encode()).decode()
    return f"v2${b64}"


def _extract_results(html: str) -> dict:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise RuntimeError("__NEXT_DATA__ not found — investing.com may be blocking")
    nd = json.loads(m.group(1))
    return nd["props"]["pageProps"]["state"]["stockScreenerStore"]["results"]


def _col_value(data: list[dict], metric: str, cols: list[str]) -> tuple[float | None, str]:
    try:
        idx = cols.index(metric)
        cell = data[idx]
        return cell.get("raw"), cell.get("value", "")
    except (ValueError, IndexError):
        return None, ""


def _parse_row(row: dict, cols: list[str]) -> ScreenerRow:
    asset = row["asset"]
    data = row["data"]

    def raw(metric: str) -> float | None:
        return _col_value(data, metric, cols)[0]

    def val(metric: str) -> str:
        return _col_value(data, metric, cols)[1]

    return ScreenerRow(
        ticker=asset.get("ticker", ""),
        name=asset.get("name", ""),
        exchange=val("investing_exchange"),
        sector=val("investing_sector"),
        industry=val("investing_industry"),
        market_cap_usd=raw("marketcap_adj_latest"),
        market_cap_display=val("marketcap_adj_latest"),
        price=raw("asset_price_latest"),
        day_change_pct=raw("asset_price_latest_change_pct"),
        pe_ratio=raw("pe_ltm_latest"),
        peg_ratio=raw("peg_ltm"),
        fair_value_label=val("fair_value_label") or None,
        analyst_target=raw("analyst_target"),
        analyst_target_upside=raw("analyst_target_upside"),
        fin_health_label=val("fin_health_overall_label") or None,
        path=asset.get("path", ""),
    )
