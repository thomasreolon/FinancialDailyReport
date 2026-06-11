"""
Screened-stocks pipeline.

Runs all screener scrapers live, deduplicates tickers across screeners, then
enriches each ticker with:
  - Yahoo Finance comprehensive profile (price, financials, estimates, etc.)
  - AnaChart analyst ratings
  - MarketBeat consensus forecast (None when exchange is unknown or scraping fails)

Usage:
    from src.pipelines.screened_stocks import run_pipeline
    result = run_pipeline()
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.scrapers.analyst.anachart import AnaChartResult, scrape_anachart
from src.scrapers.analyst.marketbeat import MarketBeatForecastResult, scrape_marketbeat_forecast
from src.scrapers.screener.investing import (
    scrape_large_cap_garp,
    scrape_mega_cap_losers,
    scrape_mid_cap_analyst_picks,
    scrape_mid_cap_losers,
    scrape_mid_cap_quality,
    scrape_small_cap_losers,
)
from src.scrapers.screener.marketbeat_golden_cross import scrape_golden_cross
from src.scrapers.screener.portfoliopilot import scrape_portfoliopilot
from src.scrapers.screener.yahoo_trending import scrape_yahoo_trending
from src.scrapers.stock.yahoo import YahooProfile, scrape_yahoo_profile

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


_MIN_LIQUID_MARKET_CAP = 500e6


def is_liquid_ticker(ticker: str, market_cap: float | None) -> bool:
    """Liquidity guard shared by selection and enrichment: excludes OTC foreign
    ADRs (5-letter tickers ending in F/Y, e.g. AYALY, AGGZF) and sub-$500M caps
    — thin books, stale quotes, unreliable analyst coverage."""
    t = ticker.upper()
    if len(t) == 5 and t[-1] in ("F", "Y"):
        return False
    return market_cap is not None and market_cap >= _MIN_LIQUID_MARKET_CAP


class ScreenedCompany(BaseModel):
    ticker: str
    sources: list[str] = Field(description="Screeners that flagged this ticker")
    yahoo: YahooProfile
    anachart: AnaChartResult | None
    marketbeat: MarketBeatForecastResult | None
    # Populated by build_report pipeline after macro snapshot is available.
    nn_score: float | None = None
    nn_predictions: dict[str, float] | None = None


class PipelineResult(BaseModel):
    companies: list[ScreenedCompany]
    total: int
    failed_tickers: list[str] = Field(default_factory=list)


def _load_tickers() -> dict[str, list[str]]:
    """Run all screener scrapers live and return {ticker: [source, ...]}."""
    tickers: dict[str, list[str]] = {}

    def add(symbol: str, source: str) -> None:
        s = symbol.upper().strip()
        if s and "-" not in s and "^" not in s:
            tickers.setdefault(s, []).append(source)

    try:
        for row in scrape_small_cap_losers(limit=15).rows:
            add(row.ticker, "small_cap_losers")
    except Exception as e:
        print(f"  [screener] small_cap_losers failed: {e}")

    try:
        for row in scrape_mid_cap_losers(limit=15).rows:
            add(row.ticker, "mid_cap_losers")
    except Exception as e:
        print(f"  [screener] mid_cap_losers failed: {e}")

    try:
        for row in scrape_mega_cap_losers(limit=15).rows:
            add(row.ticker, "mega_cap_losers")
    except Exception as e:
        print(f"  [screener] mega_cap_losers failed: {e}")

    try:
        for row in scrape_mid_cap_analyst_picks(limit=15).rows:
            add(row.ticker, "mid_cap_analyst_picks")
    except Exception as e:
        print(f"  [screener] mid_cap_analyst_picks failed: {e}")

    try:
        for row in scrape_large_cap_garp(limit=15).rows:
            add(row.ticker, "large_cap_garp")
    except Exception as e:
        print(f"  [screener] large_cap_garp failed: {e}")

    try:
        for row in scrape_mid_cap_quality(limit=15).rows:
            add(row.ticker, "mid_cap_quality")
    except Exception as e:
        print(f"  [screener] mid_cap_quality failed: {e}")

    try:
        for q in scrape_yahoo_trending(count=25).quotes:
            add(q.symbol, "yahoo_trending")
    except Exception as e:
        print(f"  [screener] yahoo_trending failed: {e}")

    try:
        for s in scrape_portfoliopilot().stocks:
            add(s.ticker, "portfoliopilot")
    except Exception as e:
        print(f"  [screener] portfoliopilot failed: {e}")

    try:
        for s in scrape_golden_cross().stocks:
            add(s.symbol, "golden_cross")
    except Exception as e:
        print(f"  [screener] golden_cross failed: {e}")

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

        anachart: AnaChartResult | None = None
        marketbeat: MarketBeatForecastResult | None = None

        # Illiquid tickers can never be selected (liquidity guard in
        # select_companies) and the NN only needs the Yahoo profile — skip the
        # expensive analyst scrapes (web_fetcher tiers / scrape.do credits).
        if not is_liquid_ticker(ticker, yahoo.market_cap):
            if verbose:
                print("ok  (illiquid — analyst enrichment skipped)")
        else:
            if verbose:
                print("ok  anachart...", end=" ", flush=True)

            try:
                anachart = scrape_anachart(ticker)
            except Exception:
                pass

            if verbose:
                print("ok  marketbeat...", end=" ", flush=True)

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
