"""
The Market Ledger — FastAPI report server.

Serves daily market reports stored in GCS, with a local-file fallback for dev.

Routes:
    GET /                       latest report (HTML)
    GET /report/{YYYY-MM-DD}    specific date (HTML)
    GET /api/latest             latest report (JSON)
    GET /api/{YYYY-MM-DD}       specific date (JSON)

Start:
    uvicorn report_server.main:app --reload --port 8000
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_BUCKET = "the-mind-financial-reports"
_PREFIX = "reports"
_LOCAL_FALLBACK = Path(__file__).parent.parent / "output" / "pipeline" / "daily_report.json"
_TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="The Market Ledger")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── GCS helpers ───────────────────────────────────────────────────────────────

def _gcs_load(blob_name: str) -> dict | None:
    try:
        from google.cloud import storage
        client = storage.Client()
        blob = client.bucket(_BUCKET).blob(blob_name)
        if not blob.exists():
            return None
        return json.loads(blob.download_as_text())
    except Exception as exc:
        print(f"[warn] GCS load failed ({blob_name}): {exc}")
        return None


def _load_latest() -> dict | None:
    data = _gcs_load(f"{_PREFIX}/latest.json")
    if data:
        return data
    if _LOCAL_FALLBACK.exists():
        return json.loads(_LOCAL_FALLBACK.read_text())
    return None


def _load_by_date(date_str: str) -> dict | None:
    return _gcs_load(f"{_PREFIX}/daily_report_{date_str}.json")


# ── Jinja2 filters ────────────────────────────────────────────────────────────

def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{'+' if v >= 0 else ''}{v:.2f}%"


def _fmt_price(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:,.2f}"


def _fmt_large(v: float | None) -> str:
    if v is None:
        return "N/A"
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"


def _fmt_date(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%A, %B %-d, %Y")
    except Exception:
        return iso_str


def _pct_class(v: float | None) -> str:
    if v is None:
        return ""
    return "ink-up" if v >= 0 else "ink-down"


templates.env.filters["fmt_pct"] = _fmt_pct
templates.env.filters["fmt_price"] = _fmt_price
templates.env.filters["fmt_large"] = _fmt_large
templates.env.filters["fmt_date"] = _fmt_date
templates.env.filters["pct_class"] = _pct_class


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    report = _load_latest()
    if not report:
        raise HTTPException(status_code=404, detail="No report available yet. Run src/run_report.py first.")
    return templates.TemplateResponse(request, "report.html", {"report": report})


@app.get("/report/{date_str}", response_class=HTMLResponse)
async def report_by_date(request: Request, date_str: str) -> HTMLResponse:
    report = _load_by_date(date_str)
    if not report:
        raise HTTPException(status_code=404, detail=f"No report found for {date_str}.")
    return templates.TemplateResponse(request, "report.html", {"report": report})


@app.get("/api/latest")
async def api_latest() -> dict:
    report = _load_latest()
    if not report:
        raise HTTPException(status_code=404, detail="No report available.")
    return report


@app.get("/api/{date_str}")
async def api_by_date(date_str: str) -> dict:
    report = _load_by_date(date_str)
    if not report:
        raise HTTPException(status_code=404, detail=f"No report for {date_str}.")
    return report
