"""Shared FRED data fetcher using the public CSV download endpoint (no API key needed)."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta

import requests

_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_series(series_id: str) -> list[tuple[date, float]]:
    resp = requests.get(_BASE, params={"id": series_id}, headers=_HEADERS, timeout=30)
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
