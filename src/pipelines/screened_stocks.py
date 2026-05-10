"""
Screened-stocks pipeline.

Reads ticker lists from the pre-scraped screener outputs in output/screener/,
deduplicates across all screeners, then enriches each ticker with:
  - Yahoo Finance comprehensive profile (price, financials, estimates, etc.)
  - AnaChart analyst ratings
  - MarketBeat consensus forecast (None when exchange is unknown or scraping fails)

Usage:
    from src.pipelines.screened_stocks import run_pipeline
    result = run_pipeline()
"""

from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel, Field

from src.scrapers.analyst.anachart import AnaChartResult, scrape_anachart
from src.scrapers.analyst.marketbeat import MarketBeatForecastResult, scrape_marketbeat_forecast
from src.scrapers.stock.yahoo import YahooProfile, scrape_yahoo_profile

_SCREENER_DIR = Path(__file__).parent.parent.parent / "output" / "screener"

# Yahoo Finance exchange name → MarketBeat URL segment (None = skip MarketBeat)
_EXCHANGE_MAP: dict[str, str | None] = {
    "NasdaqGS": "NASDAQ",
    "NasdaqGM": "NASDAQ",
    "NasdaqCM": "NASDAQ",
    "Nasdaq":   "NASDAQ",
    "NASDAQ":   "NASDAQ",
    "NYSE":     "NYSE",
    "NYSEArca": "NYSE",
    "NYSEMkt":  "NYSE",
    "AMEX":     "NYSE",
}


class ScreenedCompany(BaseModel):
    ticker: str
    sources: list[str] = Field(description="Screeners that flagged this ticker")
    yahoo: YahooProfile
    anachart: AnaChartResult | None
    marketbeat: MarketBeatForecastResult | None


class PipelineResult(BaseModel):
    companies: list[ScreenedCompany]
    total: int
    failed_tickers: list[str] = Field(default_factory=list)


def _load_tickers() -> dict[str, list[str]]:
    """Read all screener JSON files and return {ticker: [source, ...]}."""
    tickers: dict[str, list[str]] = {}

    def add(symbol: str, source: str) -> None:
        s = symbol.upper().strip()
        if s and "-" not in s and "^" not in s:
            tickers.setdefault(s, []).append(source)

    def load(filename: str) -> dict:
        path = _SCREENER_DIR / filename
        if not path.exists():
            print(f"  [screener] {filename} not found, skipping")
            return {}
        return json.loads(path.read_text())

    data = load("screener_mid_cap_losers.json")
    for row in data.get("rows", []):
        add(row["ticker"], "mid_cap_losers")

    data = load("screener_yahoo_trending.json")
    for q in data.get("quotes", []):
        add(q["symbol"], "yahoo_trending")

    data = load("screener_portfoliopilot.json")
    for s in data.get("stocks", []):
        add(s["ticker"], "portfoliopilot")

    data = load("screener_golden_cross.json")
    for s in data.get("stocks", []):
        add(s["symbol"], "golden_cross")

    return tickers


def _marketbeat_exchange(yahoo: YahooProfile) -> str | None:
    raw = yahoo.exchange or ""
    if raw in _EXCHANGE_MAP:
        return _EXCHANGE_MAP[raw]
    upper = raw.upper()
    if "NASDAQ" in upper:
        return "NASDAQ"
    if "NYSE" in upper:
        return "NYSE"
    return None


def run_pipeline(verbose: bool = True) -> PipelineResult:
    """
    Args:
        verbose: print per-ticker progress to stdout.
    """
    if verbose:
        print("Loading tickers from screener outputs...")
    tickers = _load_tickers()
    if verbose:
        print(f"  {len(tickers)} unique tickers across all screeners")

    companies: list[ScreenedCompany] = []
    failed: list[str] = []

    for ticker, sources in tickers.items():
        if verbose:
            print(f"  [{ticker}] yahoo...", end=" ", flush=True)

        try:
            yahoo = scrape_yahoo_profile(ticker)
        except Exception as e:
            if verbose:
                print(f"FAILED ({e})")
            failed.append(ticker)
            continue

        if verbose:
            print("ok  anachart...", end=" ", flush=True)

        anachart: AnaChartResult | None = None
        try:
            anachart = scrape_anachart(ticker)
        except Exception:
            pass

        if verbose:
            print("ok  marketbeat...", end=" ", flush=True)

        marketbeat: MarketBeatForecastResult | None = None
        exchange = _marketbeat_exchange(yahoo)
        if exchange:
            try:
                marketbeat = scrape_marketbeat_forecast(ticker, exchange)
            except Exception:
                pass

        if verbose:
            mb_status = "ok" if marketbeat else ("skipped" if not exchange else "failed")
            print(mb_status)

        companies.append(ScreenedCompany(
            ticker=ticker,
            sources=sources,
            yahoo=yahoo,
            anachart=anachart,
            marketbeat=marketbeat,
        ))

    return PipelineResult(
        companies=companies,
        total=len(companies),
        failed_tickers=failed,
    )
