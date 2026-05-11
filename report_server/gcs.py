"""GCS report loading with multi-layer caching.

- Today/yesterday blobs: TTL cache (5 min), re-fetched on expiry.
- Older dates: permanent @lru_cache for the process lifetime.
- find_latest(): probes today → yesterday → up to 7 days → full scan.
- list_dates(): TTL-cached list of all available dates, most-recent first.
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from functools import lru_cache

_BUCKET = "the-mind-financial-reports"
_PREFIX = "raw"
_TTL = 300.0  # seconds

# TTL cache: blob_name → (monotonic_ts, data | None)
_ttl_cache: dict[str, tuple[float, dict | None]] = {}


def _gcs_fetch(blob_name: str) -> dict | None:
    try:
        from google.cloud import storage  # type: ignore
        blob = storage.Client().bucket(_BUCKET).blob(blob_name)
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())
    except Exception as exc:
        print(f"[warn] GCS fetch failed ({blob_name}): {exc}")
        return None


def _load_ttl(blob_name: str) -> dict | None:
    now = time.monotonic()
    entry = _ttl_cache.get(blob_name)
    if entry and now - entry[0] < _TTL:
        return entry[1]
    data = _gcs_fetch(blob_name)
    _ttl_cache[blob_name] = (now, data)
    return data


@lru_cache(maxsize=64)
def _load_permanent(blob_name: str) -> dict | None:
    return _gcs_fetch(blob_name)


def _blob_for(date_str: str) -> str:
    return f"{_PREFIX}/{date_str}.json"


def load_report(date_str: str) -> dict | None:
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    blob = _blob_for(date_str)
    if date_str in (today, yesterday):
        return _load_ttl(blob)
    return _load_permanent(blob)


def find_latest() -> dict | None:
    today = date.today()
    for delta in range(7):
        d = (today - timedelta(days=delta)).isoformat()
        data = load_report(d)
        if data:
            return data
    try:
        from google.cloud import storage  # type: ignore
        blobs = sorted(
            storage.Client().bucket(_BUCKET).list_blobs(prefix=f"{_PREFIX}/daily_report_"),
            key=lambda b: b.name,
            reverse=True,
        )
        for b in blobs:
            try:
                return json.loads(b.download_as_text())
            except Exception:
                continue
    except Exception as exc:
        print(f"[warn] GCS full-scan failed: {exc}")
    return None


def load_latest() -> dict | None:
    return find_latest()


# TTL cache for list_dates
_dates_cache: tuple[float, list[str]] = (0.0, [])


def list_dates() -> list[str]:
    global _dates_cache
    now = time.monotonic()
    if now - _dates_cache[0] < _TTL:
        return _dates_cache[1]
    try:
        from google.cloud import storage  # type: ignore
        blobs = storage.Client().bucket(_BUCKET).list_blobs(prefix=f"{_PREFIX}/")
        dates: list[str] = []
        for b in blobs:
            fname = b.name.split("/")[-1]
            if fname.endswith(".json") and fname != "latest.json":
                dates.append(fname[:-len(".json")])
        dates.sort(reverse=True)
        _dates_cache = (now, dates)
        return dates
    except Exception as exc:
        print(f"[warn] GCS list_dates failed: {exc}")
        return _dates_cache[1]
