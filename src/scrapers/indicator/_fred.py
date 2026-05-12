"""Shared FRED data fetcher.

Primary: official FRED JSON API (api.stlouisfed.org) when FRED_API_KEY is set.
Fallback: public CSV download endpoint (fredgraph.csv) — blocked on some cloud IPs.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import date, timedelta

import requests

_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_API_BASE = "https://api.stlouisfed.org/fred/series/observations"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _api_key() -> str | None:
    return os.environ.get("FRED_API_KEY")


def _fetch_via_api(series_id: str) -> list[tuple[date, float]]:
    resp = requests.get(
        _API_BASE,
        params={
            "series_id": series_id,
            "api_key": _api_key(),
            "file_type": "json",
            "sort_order": "asc",
        },
        headers=_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    result: list[tuple[date, float]] = []
    for obs in resp.json().get("observations", []):
        val_str = obs.get("value", "").strip()
        if val_str in (".", ""):
            continue
        try:
            result.append((date.fromisoformat(obs["date"]), float(val_str)))
        except (ValueError, KeyError):
            continue
    return result


def _fetch_via_csv(series_id: str) -> list[tuple[date, float]]:
    resp = requests.get(_CSV_BASE, params={"id": series_id}, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    result: list[tuple[date, float]] = []
    reader = csv.reader(io.StringIO(resp.text))
    next(reader)  # skip header
    for row in reader:
        if len(row) < 2 or row[1].strip() in (".", ""):
            continue
        try:
            result.append((date.fromisoformat(row[0].strip()), float(row[1].strip())))
        except (ValueError, IndexError):
            continue
    return result


def fetch_series(series_id: str) -> list[tuple[date, float]]:
    if _api_key():
        return _fetch_via_api(series_id)
    return _fetch_via_csv(series_id)


def get_latest(series_id: str) -> tuple[date, float]:
    rows = fetch_series(series_id)
    if not rows:
        raise ValueError(f"No data returned for FRED series {series_id}")
    return rows[-1]


def get_yoy(series_id: str) -> tuple[date, float, float | None]:
    """Returns (date, latest_value, yoy_pct). yoy_pct is None if year-ago data unavailable."""
    rows = fetch_series(series_id)
    if not rows:
        raise ValueError(f"No data returned for FRED series {series_id}")
    latest_date, latest_val = rows[-1]
    target = latest_date.replace(year=latest_date.year - 1)
    best_diff = timedelta.max
    year_ago_val: float | None = None
    for d, v in rows:
        diff = abs(d - target)
        if diff < best_diff:
            best_diff = diff
            year_ago_val = v
    yoy: float | None = None
    if year_ago_val and year_ago_val != 0:
        yoy = round((latest_val - year_ago_val) / abs(year_ago_val) * 100, 2)
    return (latest_date, latest_val, yoy)


def get_mom(series_id: str) -> tuple[date, float, float | None]:
    """Returns (date, latest_value, mom_pct). For monthly series."""
    rows = fetch_series(series_id)
    if not rows:
        raise ValueError(f"No data returned for FRED series {series_id}")
    latest_date, latest_val = rows[-1]
    prev_val = rows[-2][1] if len(rows) >= 2 else None
    mom: float | None = None
    if prev_val and prev_val != 0:
        mom = round((latest_val - prev_val) / abs(prev_val) * 100, 2)
    return (latest_date, latest_val, mom)
