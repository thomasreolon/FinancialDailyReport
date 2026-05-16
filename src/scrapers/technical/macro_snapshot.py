"""
Macro snapshot for the ff_analysis model — session-count return windows and
levels that the model's feature engineering expects but that the existing
macro_indicators pipeline does not produce.

Data sources:
  - Yahoo chart API (no auth, curl_cffi):
        ^VIX, ^TNX (10Y yield, %), ^GSPC (S&P 500), CL=F (WTI), EURUSD=X
  - FRED (reusing src/scrapers/indicator/_fred.py):
        DGS2 (2Y Treasury yield, %) — for t10y2y = DGS10 − DGS2
        BAMLH0A0HYM2 (ICE BofA US High Yield OAS, %) — HY spread

Outputs are flat fields chosen to match the keys json_to_features.py reads
from its `macro_sup` dict, so the JSON can be consumed downstream without
remapping. Every individual fetch is wrapped in try/except — a failure
leaves the corresponding fields None instead of breaking the snapshot.

Return-window convention: SESSION COUNTS (trading-day bars), not calendar days.
This mirrors how the ff_analysis model was trained.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
    "Accept": "application/json",
}

# Trading-day windows the ff_analysis model uses for sp500_ret_* and wti_ret_*.
_RET_HORIZONS: tuple[tuple[int, str], ...] = (
    (5,   "5d"),
    (21,  "21d"),
    (126, "126d"),
    (378, "378d"),
)


class MacroSnapshot(BaseModel):
    # Levels
    vix:        float | None = None    # VIX index level
    dgs10:      float | None = None    # 10Y Treasury yield (%)
    dgs2:       float | None = None    # 2Y Treasury yield (%)
    t10y2y:     float | None = None    # DGS10 − DGS2 (%)
    hy_spread:  float | None = None    # BAMLH0A0HYM2 OAS (%)
    usd_eur:    float | None = None    # USD per 1 EUR (EURUSD=X last close)

    # Session-count returns (in percent, e.g. 1.23 means +1.23%)
    sp500_ret_5d:   float | None = None
    sp500_ret_21d:  float | None = None
    sp500_ret_126d: float | None = None
    sp500_ret_378d: float | None = None
    wti_ret_5d:   float | None = None
    wti_ret_21d:  float | None = None
    wti_ret_126d: float | None = None
    wti_ret_378d: float | None = None

    fetched_at: str = ""
    sources:    dict[str, str] = {}    # field → data source/date


# ── helpers ───────────────────────────────────────────────────────────────────

def _chart_closes(
    session: cf_requests.Session,
    symbol: str,
    timeout: int = 30,
) -> tuple[list[float], int | None]:
    """Return (valid_closes_oldest_first, last_timestamp). Empty on failure."""
    try:
        resp = session.get(
            _CHART_URL.format(symbol=symbol),
            headers=_HEADERS,
            params={"interval": "1d", "range": "3y", "includePrePost": "false"},
            timeout=timeout,
        )
        resp.raise_for_status()
        result = (resp.json().get("chart", {}).get("result") or [None])[0]
        if not result:
            return [], None
        ts = result.get("timestamp") or []
        closes = ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
        valid: list[float] = [c for c in closes if c is not None and c > 0 and math.isfinite(c)]
        last_ts = ts[-1] if ts else None
        return valid, last_ts
    except Exception:
        return [], None


def _last_level(valid: list[float]) -> float | None:
    return valid[-1] if valid else None


def _bar_ret(valid: list[float], n: int) -> float | None:
    if len(valid) > n and valid[-1 - n] > 0:
        return round((valid[-1] - valid[-1 - n]) / valid[-1 - n] * 100.0, 4)
    return None


# ── public API ────────────────────────────────────────────────────────────────

class MacroSnapshotNode(ScrapingNode):
    def scrape(self) -> MacroSnapshot | None:
        return scrape_macro_snapshot()


def scrape_macro_snapshot(timeout: int = 30) -> MacroSnapshot:
    session = cf_requests.Session(impersonate="chrome124")
    snap = MacroSnapshot(fetched_at=datetime.now(timezone.utc).isoformat())

    # — Yahoo chart series —
    yahoo_targets = {
        "^VIX":     "vix",
        "^TNX":     "dgs10",       # ^TNX is 10Y yield expressed in percent (e.g. 4.32)
        "^GSPC":    "sp500",
        "CL=F":     "wti",
        "EURUSD=X": "eurusd",
    }
    closes_by_tag: dict[str, list[float]] = {}
    for sym, tag in yahoo_targets.items():
        valid, _ = _chart_closes(session, sym, timeout=timeout)
        closes_by_tag[tag] = valid
        if valid:
            snap.sources[tag] = f"Yahoo chart {sym}"

    snap.vix     = _last_level(closes_by_tag.get("vix", []))
    snap.dgs10   = _last_level(closes_by_tag.get("dgs10", []))
    snap.usd_eur = _last_level(closes_by_tag.get("eurusd", []))

    for n, suf in _RET_HORIZONS:
        setattr(snap, f"sp500_ret_{suf}", _bar_ret(closes_by_tag.get("sp500", []), n))
        setattr(snap, f"wti_ret_{suf}",   _bar_ret(closes_by_tag.get("wti", []),   n))

    # — FRED series (DGS2 + HY spread) —
    try:
        from src.scrapers.indicator._fred import get_latest
        d2_date, d2_val = get_latest("DGS2")
        snap.dgs2 = round(float(d2_val), 4)
        snap.sources["dgs2"] = f"FRED DGS2 ({d2_date})"
    except Exception:
        pass

    try:
        from src.scrapers.indicator._fred import get_latest
        hy_date, hy_val = get_latest("BAMLH0A0HYM2")
        snap.hy_spread = round(float(hy_val), 4)
        snap.sources["hy_spread"] = f"FRED BAMLH0A0HYM2 ({hy_date})"
    except Exception:
        pass

    if snap.dgs10 is not None and snap.dgs2 is not None:
        snap.t10y2y = round(snap.dgs10 - snap.dgs2, 4)

    return snap
