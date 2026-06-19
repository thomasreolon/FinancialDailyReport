"""
World Government Bonds sovereign CDS scraper — 5-year credit default swap
spreads for the United States, Italy, and Germany.

Calls the site's own wp-json/common/v1/historical endpoint directly (no
browser needed). Discovered by intercepting the XHR traffic the page's own
JS fires when rendering its chart — the endpoint requires only an Origin
header (no auth/cookies), and returns full daily history back to ~2017.

Period returns are computed the same way as market_overview.py: a fixed
"on or before" lookup against the daily close series. US/Italy/Germany
history goes back to 2017, well past 3 years, so unlike the ETF spark feed
there's no boundary risk on the 3-year column.

Italy + Germany alongside the US gives the classic peripheral-vs-core
Eurozone risk read (the "BTP-Bund" sovereign spread), in addition to the
US benchmark.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

_URL = "https://www.worldgovernmentbonds.com/wp-json/common/v1/historical"
_HEADERS = {
    "Content-Type": "application/json; charset=UTF-8",
    "Origin": "https://www.worldgovernmentbonds.com",
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# (display symbol, display name, WGB internal country SYMBOL code, URL slug)
_COUNTRIES: list[tuple[str, str, str, str]] = [
    ("US-CDS5Y", "US 5Y CDS", "6", "united-states"),
    ("IT-CDS5Y", "Italy 5Y CDS", "1", "italy"),
    ("DE-CDS5Y", "Germany 5Y CDS", "2", "germany"),
]


class CDSPerformance(BaseModel):
    symbol: str
    name: str
    current_bp: float | None
    today_pct: float | None
    five_day_pct: float | None
    one_month_pct: float | None
    one_year_pct: float | None
    three_year_pct: float | None


def _price_at(valid: list[tuple[date, float]], target: date) -> float | None:
    """Last available close on or before target date."""
    result: float | None = None
    for d, v in valid:
        if d <= target:
            result = v
        else:
            break
    return result


def _pct(current: float, past: float | None) -> float | None:
    if past is None or past == 0:
        return None
    return round((current - past) / past * 100, 2)


def _empty(symbol: str, name: str) -> CDSPerformance:
    return CDSPerformance(
        symbol=symbol, name=name, current_bp=None,
        today_pct=None, five_day_pct=None, one_month_pct=None,
        one_year_pct=None, three_year_pct=None,
    )


def _fetch_country(
    session: cf_requests.Session,
    symbol: str, name: str, wgb_code: str, slug: str,
    timeout: int,
) -> CDSPerformance:
    payload = {
        "GLOBALVAR": {
            "JS_VARIABLE": "jsGlobalVars",
            "FUNCTION": "CDS",
            "DOMESTIC": True,
            "ENDPOINT": _URL,
            "DATE_RIF": "2099-12-31",
            "DEBUG": True,
            "OBJ": {"UNIT": "", "DECIMAL": 2, "UNIT_DELTA": "%", "DECIMAL_DELTA": 2},
            "COUNTRY1": {
                "SYMBOL": wgb_code,
                "PAESE": name,
                "PAESE_UPPERCASE": name.upper(),
                "BANDIERA": slug[:2],
                "URL_PAGE": slug,
            },
            "COUNTRY2": None,
            "OBJ1": {"DURATA_STRING": "5 Years", "DURATA": 60},
            "OBJ2": None,
        }
    }
    headers = {
        **_HEADERS,
        "Referer": f"https://www.worldgovernmentbonds.com/cds-historical-data/{slug}/5-years/",
    }
    resp = session.post(_URL, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    quote = resp.json().get("result", {}).get("quote", {})

    points: list[tuple[date, float]] = sorted(
        (
            (datetime.strptime(q["DATA_VAL"], "%Y-%m-%d").date(), q["CLOSE_VAL"])
            for q in quote.values()
            if q.get("DATA_VAL") and q.get("CLOSE_VAL") is not None
        ),
        key=lambda x: x[0],
    )
    if not points:
        return _empty(symbol, name)

    current = points[-1][1]
    today = date.today()

    return CDSPerformance(
        symbol=symbol,
        name=name,
        current_bp=current,
        today_pct=_pct(current, points[-2][1] if len(points) >= 2 else None),
        five_day_pct=_pct(current, points[-6][1] if len(points) >= 6 else None),
        one_month_pct=_pct(current, _price_at(points, today - timedelta(days=30))),
        one_year_pct=_pct(current, _price_at(points, today - timedelta(days=365))),
        three_year_pct=_pct(current, _price_at(points, today - timedelta(days=3 * 365))),
    )


def scrape_sovereign_cds(timeout: int = 30) -> list[CDSPerformance]:
    session = cf_requests.Session(impersonate="chrome124")
    result = []
    for symbol, name, wgb_code, slug in _COUNTRIES:
        try:
            result.append(_fetch_country(session, symbol, name, wgb_code, slug, timeout))
        except Exception:
            result.append(_empty(symbol, name))
    return result
