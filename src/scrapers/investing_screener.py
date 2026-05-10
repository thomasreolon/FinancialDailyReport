"""
Screener for mid-cap US stocks sorted by worst daily change.

Usage:
    from src.scrapers.investing_screener import scrape_mid_cap_losers, ScreenerRow

    rows = scrape_mid_cap_losers(limit=30)
    for r in rows:
        print(r.ticker, r.name, r.day_change_pct)
"""

import base64
import json
import re

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

# ── constants ─────────────────────────────────────────────────────────────────

_SCREENER_URL = "https://www.investing.com/stock-screener"
_NEXT_DATA_RE  = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)

# Mid-cap: $2B–$10B USD  (adjust freely)
_MID_CAP_LOW  = 2_000_000_000
_MID_CAP_HIGH = 10_000_000_000


# ── models ────────────────────────────────────────────────────────────────────

class ScreenerRow(BaseModel):
    ticker: str
    name: str
    exchange: str
    sector: str
    industry: str
    market_cap_usd: float | None
    market_cap_display: str
    price: float | None
    day_change_pct: float | None         # e.g. -0.186 for -18.6%
    pe_ratio: float | None
    peg_ratio: float | None
    fair_value_label: str | None
    analyst_target: float | None
    analyst_target_upside: float | None
    fin_health_label: str | None
    path: str                            # investing.com relative path (e.g. /equities/...)


class ScreenerResult(BaseModel):
    rows: list[ScreenerRow]
    total_in_universe: int


# ── ssid construction ─────────────────────────────────────────────────────────

def _make_ssid(
    market: str = "US",
    mktcap_low: float = _MID_CAP_LOW,
    mktcap_high: float = _MID_CAP_HIGH,
    sort_metric: str = "asset_price_latest_change_pct",
    sort_dir: str = "ASC",
    page_size: int = 30,
) -> str:
    """
    Encode a query as a screener ssid (v2$<base64>).
    The ssid is placed in the URL so the server-side render fetches filtered data.
    """
    # The preset hex encodes the market-cap range filter
    preset_obj = {
        "keys": [
            "currency", "gt.inclusive", "gt.scale", "gt.value",
            "lt.inclusive", "lt.scale", "lt.value", "metric",
        ],
        "values": [
            "USD", True, 1, mktcap_low,
            True, 1, mktcap_high, "marketcap_adj_latest",
        ],
    }
    preset_hex = json.dumps(preset_obj, separators=(",", ":")).encode().hex()

    ssid_obj = {
        "keys": [
            "connective",
            "filters.0.metric", "filters.0.preset",
            "limit",
            "prefilters.market", "prefilters.primaryOnly",
            "sort.direction", "sort.metric",
        ],
        "values": [
            "ALL",
            "marketcap_adj_latest", preset_hex,
            page_size,
            market, False,
            sort_dir, sort_metric,
        ],
    }
    b64 = base64.b64encode(json.dumps(ssid_obj, separators=(",", ":")).encode()).decode()
    return f"v2${b64}"


# ── HTML fetching ─────────────────────────────────────────────────────────────

def _fetch_screener_html(ssid: str, timeout: int = 30) -> str:
    url = f"{_SCREENER_URL}?ssid={ssid}"
    resp = cf_requests.get(
        url,
        impersonate="chrome124",
        timeout=timeout,
        headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.investing.com/",
        },
    )
    resp.raise_for_status()
    return resp.text


def _extract_results(html: str) -> dict:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise RuntimeError("__NEXT_DATA__ not found in screener HTML — page may be blocked")
    nd = json.loads(m.group(1))
    state = nd["props"]["pageProps"]["state"]
    return state["stockScreenerStore"]["results"]


# ── row parsing ───────────────────────────────────────────────────────────────

_METRIC_IDX: dict[str, int] = {}  # filled per-response


def _col_value(data: list[dict], metric: str, cols: list[str]) -> tuple[float | None, str]:
    """Return (raw_float, display_string) for a given metric column."""
    try:
        idx = cols.index(metric)
        cell = data[idx]
        return cell.get("raw"), cell.get("value", "")
    except (ValueError, IndexError):
        return None, ""


def _parse_row(row: dict, cols: list[str]) -> ScreenerRow:
    asset = row["asset"]
    data  = row["data"]

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


# ── public API ────────────────────────────────────────────────────────────────

def scrape_mid_cap_losers(
    limit: int = 30,
    market: str = "US",
    mktcap_low: float = _MID_CAP_LOW,
    mktcap_high: float = _MID_CAP_HIGH,
    timeout: int = 30,
) -> ScreenerResult:
    """
    Return up to `limit` mid-cap US stocks sorted by worst day % change.

    Args:
        limit:      Max rows to return (server caps at 30 per fetch).
        market:     Investing.com market code (default "US").
        mktcap_low: Lower market-cap bound in USD (default $2B).
        mktcap_high: Upper market-cap bound in USD (default $10B).
        timeout:    HTTP timeout in seconds.

    Returns:
        ScreenerResult with rows sorted ascending by day_change_pct (worst first)
        and total_in_universe showing how many stocks matched the filter overall.
    """
    ssid = _make_ssid(market, mktcap_low, mktcap_high, page_size=min(limit, 30))
    html = _fetch_screener_html(ssid, timeout=timeout)
    res  = _extract_results(html)

    cols  = [c["metric"] for c in res.get("columns", [])]
    rows  = res.get("rows", [])
    total = res.get("page", {}).get("totalItems", 0)

    return ScreenerResult(
        rows=[_parse_row(r, cols) for r in rows[:limit]],
        total_in_universe=total,
    )
