"""
The Market Ledger — FastAPI report server.

Routes:
    GET /                       redirect to latest report
    GET /{YYYY-MM-DD}           report with navigation shell
    GET /raw/{YYYY-MM-DD}       bare report HTML (for iframe)
    GET /api/latest             latest report JSON
    GET /api/{YYYY-MM-DD}       specific date JSON
    GET /health                 health check
    GET /robots.txt             robots disallow file

Start:
    uvicorn report_server.main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from report_server import gcs, limiter
from report_server.yahoo_quotes import fetch_spark_prices, parse_symbols_param

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="The Market Ledger")
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── Rate limiter middleware ───────────────────────────────────────────────────

class _RateLimiter(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        ip = request.client.host if request.client else "unknown"
        if not limiter.is_allowed(ip):
            return Response("Too Many Requests", status_code=429)
        return await call_next(request)


app.add_middleware(_RateLimiter)


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


def _fmt_ratio(v: float | None) -> str:
    """Format a 0–1 decimal as a percentage (e.g. 0.42 → '42.0%')."""
    if v is None:
        return "N/A"
    return f"{v * 100:.1f}%"


def _fmt_ind(v: float | None, unit: str = "") -> str:
    """Format a normalized indicator value for display."""
    if v is None:
        return "—"
    if unit == "T$":
        return f"${v:.2f}T"
    if unit == "B$":
        return f"${v:.0f}B"
    if unit == "pct+":
        return f"{v:+.2f}%"
    if unit == "pct":
        return f"{v:.2f}%"
    if unit == "x":
        return f"{v:.1f}x"
    # dimensionless: auto precision
    if abs(v) >= 1000:
        return f"{v:,.1f}"
    if abs(v) >= 100:
        return f"{v:.1f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    if abs(v) >= 0.001:
        return f"{v:.5f}"
    return f"{v:.6f}"


def _pct_class(v: float | None, invert: bool = False) -> str:
    if v is None:
        return ""
    up = v >= 0
    if invert:
        up = not up
    return "ink-up" if up else "ink-down"


templates.env.filters["fmt_pct"] = _fmt_pct
templates.env.filters["fmt_price"] = _fmt_price
templates.env.filters["fmt_large"] = _fmt_large
templates.env.filters["fmt_date"] = _fmt_date
templates.env.filters["fmt_ratio"] = _fmt_ratio
templates.env.filters["fmt_ind"] = _fmt_ind
templates.env.filters["pct_class"] = _pct_class


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> str:
    return "User-agent: *\nDisallow: /api/\n"


@app.get("/api/latest")
async def api_latest() -> dict:
    report = gcs.load_latest()
    if not report:
        raise HTTPException(status_code=404, detail="No report available.")
    return report


@app.get("/api/quote")
async def api_quote(symbols: str = "") -> dict:
    """
    Same-origin proxy for selected-company live prices (browser cannot call Yahoo
    directly: CORS + quote API 401). Response shape matches the old client-side
    Yahoo /v7/finance/quote JSON for minimal template changes.
    """
    parsed = parse_symbols_param(symbols)
    if not parsed:
        return {"quoteResponse": {"result": [], "error": None}}
    rows = await asyncio.to_thread(fetch_spark_prices, parsed)
    return {"quoteResponse": {"result": rows, "error": None}}


@app.get("/api/{date_str}")
async def api_by_date(date_str: str) -> dict:
    report = gcs.load_report(date_str)
    if not report:
        raise HTTPException(status_code=404, detail=f"No report for {date_str}.")
    return report


@app.get("/", response_class=HTMLResponse)
async def index() -> RedirectResponse:
    dates = gcs.list_dates()
    if dates:
        return RedirectResponse(url=f"/{dates[0]}", status_code=302)
    data = gcs.load_latest()
    if data and (gen := data.get("report", {}).get("generated_at")):
        return RedirectResponse(url=f"/{gen[:10]}", status_code=302)
    raise HTTPException(status_code=404, detail="No report available yet. Run src/run_report.py first.")


@app.get("/raw/{date_str}", response_class=HTMLResponse)
async def raw_report(request: Request, date_str: str) -> HTMLResponse:
    data = gcs.load_report(date_str)
    if not data or "report" not in data:
        raise HTTPException(status_code=404, detail=f"No report found for {date_str}.")
    return templates.TemplateResponse(request, "report.html", {"report": data["report"]})


@app.get("/{date_str}", response_class=HTMLResponse)
async def shell(request: Request, date_str: str) -> HTMLResponse:
    dates = gcs.shell_date_options(date_str)
    return templates.TemplateResponse(request, "shell.html", {
        "date_str": date_str,
        "dates": dates,
    })
