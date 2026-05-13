"""
US stocks sorted by worst daily % change — investing.com screener, by cap tier.

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
_SMALL_CAP_LOW  =       300_000_000   # $300M
_SMALL_CAP_HIGH =     2_000_000_000   # $2B
_MID_CAP_LOW    =     2_000_000_000   # $2B
_MID_CAP_HIGH   =    10_000_000_000   # $10B
_MEGA_CAP_LOW   =    10_000_000_000   # $10B
_MEGA_CAP_HIGH  =   200_000_000_000  # $10T — practical ceiling


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


class SmallCapLosersNode(ScrapingNode):
    def __init__(self, limit: int = 15, market: str = "US"):
        self.limit = limit
        self.market = market

    def scrape(self) -> ScreenerResult | None:
        return scrape_small_cap_losers(limit=self.limit, market=self.market)


class MidCapLosersNode(ScrapingNode):
    def __init__(self, limit: int = 15, market: str = "US"):
        self.limit = limit
        self.market = market

    def scrape(self) -> ScreenerResult | None:
        return scrape_mid_cap_losers(limit=self.limit, market=self.market)


class MegaCapLosersNode(ScrapingNode):
    def __init__(self, limit: int = 15, market: str = "US"):
        self.limit = limit
        self.market = market

    def scrape(self) -> ScreenerResult | None:
        return scrape_mega_cap_losers(limit=self.limit, market=self.market)


class LargeCapGARPNode(ScrapingNode):
    def __init__(self, limit: int = 15, market: str = "US"):
        self.limit = limit
        self.market = market

    def scrape(self) -> ScreenerResult | None:
        return scrape_large_cap_garp(limit=self.limit, market=self.market)


class MidCapQualityNode(ScrapingNode):
    def __init__(self, limit: int = 15, market: str = "US"):
        self.limit = limit
        self.market = market

    def scrape(self) -> ScreenerResult | None:
        return scrape_mid_cap_quality(limit=self.limit, market=self.market)


class MidCapAnalystPicksNode(ScrapingNode):
    def __init__(self, limit: int = 15, market: str = "US"):
        self.limit = limit
        self.market = market

    def scrape(self) -> ScreenerResult | None:
        return scrape_mid_cap_analyst_picks(limit=self.limit, market=self.market)


def scrape_small_cap_losers(limit: int = 15, market: str = "US", timeout: int = 30) -> ScreenerResult:
    return _scrape_losers(_SMALL_CAP_LOW, _SMALL_CAP_HIGH, limit, market, timeout)


def scrape_mid_cap_losers(limit: int = 15, market: str = "US", timeout: int = 30) -> ScreenerResult:
    return _scrape_losers(_MID_CAP_LOW, _MID_CAP_HIGH, limit, market, timeout)


def scrape_mega_cap_losers(limit: int = 15, market: str = "US", timeout: int = 30) -> ScreenerResult:
    return _scrape_losers(_MEGA_CAP_LOW, _MEGA_CAP_HIGH, limit, market, timeout)


def scrape_large_cap_garp(limit: int = 15, market: str = "US", timeout: int = 30) -> ScreenerResult:
    """Large-cap ($10B–$200B) GARP: NI > 0, EBITDA > 0, PEG favorable (0–1), sorted by market cap desc."""
    obj = {
        "connective": "ALL",
        "filters.0.currency": "USD",
        "filters.0.gt.inclusive": False,
        "filters.0.gt.scale": 1_000_000_000,
        "filters.0.gt.value": 10,
        "filters.0.lt.inclusive": False,
        "filters.0.lt.scale": 1_000_000_000,
        "filters.0.lt.value": 200,
        "filters.0.metric": "marketcap_adj_latest",
        "filters.1.currency": "USD",
        "filters.1.gt.inclusive": True,
        "filters.1.gt.scale": 1,
        "filters.1.gt.value": 0,
        "filters.1.metric": "ebitda",
        "filters.2.currency": "USD",
        "filters.2.gt.inclusive": True,
        "filters.2.gt.scale": 1,
        "filters.2.gt.value": 0,
        "filters.2.metric": "ni",
        "filters.3.gt.inclusive": False,
        "filters.3.gt.scale": 1,
        "filters.3.gt.value": 0,
        "filters.3.lt.inclusive": False,
        "filters.3.lt.scale": 1,
        "filters.3.lt.value": 1,
        "filters.3.metric": "peg_ltm",
        "limit": min(limit, 30),
        "prefilters.market": market,
        "prefilters.primaryOnly": True,
        "sort.direction": "DESC",
        "sort.metric": "marketcap_adj_latest",
    }
    return _scrape_losers_flat(obj, limit, timeout)


def scrape_mid_cap_quality(limit: int = 15, market: str = "US", timeout: int = 30) -> ScreenerResult:
    """Mid-cap quality compounder: EBITDA/NI/EBIT > 0, PEG favorable, EV/EBITDA low (1–10)."""
    obj = {
        "connective": "ALL",
        "filters.0.currency": "USD",
        "filters.0.gt.inclusive": False,
        "filters.0.gt.scale": 1_000_000_000,
        "filters.0.gt.value": 2,
        "filters.0.lt.inclusive": False,
        "filters.0.lt.scale": 1_000_000_000,
        "filters.0.lt.value": 10,
        "filters.0.metric": "marketcap_adj_latest",
        "filters.1.currency": "USD",
        "filters.1.gt.inclusive": True,
        "filters.1.gt.scale": 1,
        "filters.1.gt.value": 0,
        "filters.1.metric": "ebitda",
        "filters.2.currency": "USD",
        "filters.2.gt.inclusive": True,
        "filters.2.gt.scale": 1,
        "filters.2.gt.value": 0,
        "filters.2.metric": "ni",
        "filters.3.currency": "USD",
        "filters.3.gt.inclusive": True,
        "filters.3.gt.scale": 1,
        "filters.3.gt.value": 0,
        "filters.3.metric": "ebit",
        "filters.4.gt.inclusive": False,
        "filters.4.gt.scale": 1,
        "filters.4.gt.value": 0,
        "filters.4.lt.inclusive": False,
        "filters.4.lt.scale": 1,
        "filters.4.lt.value": 1,
        "filters.4.metric": "peg_ltm",
        "filters.5.gt.inclusive": True,
        "filters.5.gt.scale": 1,
        "filters.5.gt.value": 1,
        "filters.5.lt.inclusive": True,
        "filters.5.lt.scale": 1,
        "filters.5.lt.value": 10,
        "filters.5.metric": "ev_to_ebitda_ltm",
        "limit": min(limit, 30),
        "prefilters.market": market,
        "prefilters.primaryOnly": True,
        "sort.direction": "DESC",
        "sort.metric": "marketcap_adj_latest",
    }
    return _scrape_losers_flat(obj, limit, timeout)


def scrape_mid_cap_analyst_picks(limit: int = 15, market: str = "US", timeout: int = 30) -> ScreenerResult:
    """Mid-cap profitable stocks (EBITDA > 0) with analyst upside 18–50%, sorted by market cap desc."""
    obj = {
        "connective": "ALL",
        "filters.0.gt.inclusive": True,
        "filters.0.gt.scale": 1,
        "filters.0.gt.value": 0.18,
        "filters.0.lt.inclusive": True,
        "filters.0.lt.scale": 1,
        "filters.0.lt.value": 0.5,
        "filters.0.metric": "analyst_target_upside",
        "filters.1.currency": "USD",
        "filters.1.gt.inclusive": False,
        "filters.1.gt.scale": 1_000_000_000,
        "filters.1.gt.value": 2,
        "filters.1.lt.inclusive": False,
        "filters.1.lt.scale": 1_000_000_000,
        "filters.1.lt.value": 10,
        "filters.1.metric": "marketcap_adj_latest",
        "filters.2.currency": "USD",
        "filters.2.gt.inclusive": True,
        "filters.2.gt.scale": 1,
        "filters.2.gt.value": 0,
        "filters.2.metric": "ebitda",
        "limit": min(limit, 30),
        "prefilters.market": market,
        "prefilters.primaryOnly": True,
        "sort.direction": "DESC",
        "sort.metric": "marketcap_adj_latest",
    }
    return _scrape_losers_flat(obj, limit, timeout)


def _scrape_losers(
    mktcap_low: float,
    mktcap_high: float,
    limit: int,
    market: str,
    timeout: int,
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


def _scrape_losers_flat(obj: dict, limit: int, timeout: int) -> ScreenerResult:
    ssid = _make_ssid_flat(obj)
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


def _make_ssid_flat(obj: dict) -> str:
    """Build a v2 ssid from a flat ordered key→value dict (multi-filter format)."""
    ssid_obj = {"keys": list(obj.keys()), "values": list(obj.values())}
    b64 = base64.b64encode(json.dumps(ssid_obj, separators=(",", ":")).encode()).decode()
    return f"v2${b64}"


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
