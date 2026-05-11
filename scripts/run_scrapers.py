"""
Run all registered scrapers and save results to output/screener/.

To add a new scraper, append an entry to SCRAPERS at the bottom of this file:

    ("my_scraper_name", lambda: my_scrape_function(...))

The callable must return a Pydantic BaseModel, a list of BaseModels, or None.
None results are skipped (no file written).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel

OUTPUT_DIR = ROOT / "output" / "screener"


def _serialize(result: BaseModel | list) -> str:
    if isinstance(result, list):
        return json.dumps([r.model_dump(mode="json") for r in result], indent=2, default=str)
    return result.model_dump_json(indent=2)


def run_scrapers(scrapers: list[tuple[str, Callable]]) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    ok = failed = skipped = 0

    for name, fn in scrapers:
        print(f"  {name}...", end=" ", flush=True)
        try:
            result = fn()
            if result is None:
                print("skipped (returned None)")
                skipped += 1
                continue
            out_path = OUTPUT_DIR / f"{name}.json"
            out_path.write_text(_serialize(result))
            print(f"saved → {out_path.relative_to(ROOT)}")
            ok += 1
        except Exception as exc:
            print(f"FAILED: {exc}")
            failed += 1

    print(f"\n  {ok} saved  {skipped} skipped  {failed} failed")
    if failed:
        sys.exit(1)


# ── scraper registry ──────────────────────────────────────────────────────────
# Add new scrapers here: ("output_filename", lambda: scrape_function(...))

if __name__ == "__main__":
    from src.scrapers.screener.investing import scrape_mid_cap_losers
    from src.scrapers.screener.yahoo_trending import scrape_yahoo_trending
    from src.scrapers.screener.portfoliopilot import scrape_portfoliopilot
    from src.scrapers.screener.marketbeat_golden_cross import scrape_golden_cross
    from src.scrapers.news.ft_world import scrape_ft_world
    from src.scrapers.news.stonex import scrape_stonex
    from src.scrapers.news.tikr_blog import scrape_tikr_blog
    from src.scrapers.news.yt_scraper import YTScraper
    from src.scrapers.analyst.anachart import scrape_anachart
    from src.scrapers.analyst.marketbeat import scrape_marketbeat_forecast
    from src.scrapers.stock.investing import scrape_investing_stock
    from src.scrapers.stock.yahoo import scrape_yahoo_profile
    from src.scrapers.technical.market_overview import scrape_market_overview
    from src.scrapers.technical.sentiment_outlook import scrape_sentiment_outlook
    from src.scrapers.indicator.vix import scrape_vix
    from src.scrapers.indicator.fear_greed import scrape_fear_greed
    from src.scrapers.indicator.yield_curve import scrape_yield_curve
    from src.scrapers.indicator.fed_funds_rate import scrape_fed_funds_rate
    from src.scrapers.indicator.fed_june_probability import scrape_fed_june_probability
    from src.scrapers.indicator.fed_balance_sheet import scrape_fed_balance_sheet
    from src.scrapers.indicator.m2_us import scrape_m2_us
    from src.scrapers.indicator.global_m2 import scrape_global_m2
    from src.scrapers.indicator.rrp_facility import scrape_rrp_facility
    from src.scrapers.indicator.margin_debt import scrape_margin_debt
    from src.scrapers.indicator.spy_m2_ratio import scrape_spy_m2_ratio
    from src.scrapers.indicator.breakeven_5y import scrape_breakeven_5y
    from src.scrapers.indicator.breakeven_10y import scrape_breakeven_10y
    from src.scrapers.indicator.core_pce import scrape_core_pce
    from src.scrapers.indicator.ism_pmi import scrape_ism_pmi
    from src.scrapers.indicator.shiller_cape import scrape_shiller_cape
    from src.scrapers.indicator.buffett_indicator import scrape_buffett_indicator
    from src.scrapers.indicator.equity_risk_premium import scrape_equity_risk_premium
    from src.scrapers.indicator.lei import scrape_lei
    from src.scrapers.indicator.copper_gold_ratio import scrape_copper_gold_ratio
    from src.scrapers.indicator.sp500_fwd_eps import scrape_sp500_fwd_eps
    from src.scrapers.indicator.sp500_fwd_pe import scrape_sp500_fwd_pe
    from src.scrapers.indicator.sp500_eps_growth import scrape_sp500_eps_growth
    from src.scrapers.indicator.eurostoxx50_fwd_eps import scrape_eurostoxx50_fwd_eps
    from src.scrapers.indicator.leading_sectors import scrape_leading_sectors

    SCRAPERS: list[tuple[str, Callable]] = [
        # ── screeners ──────────────────────────────────────────────────────────
        ("screener_mid_cap_losers",    lambda: scrape_mid_cap_losers(limit=30)),
        ("screener_yahoo_trending",    lambda: scrape_yahoo_trending(count=25)),
        ("screener_portfoliopilot",    lambda: scrape_portfoliopilot()),
        ("screener_golden_cross",      lambda: scrape_golden_cross()),
        # ── news ───────────────────────────────────────────────────────────────
        ("news_ft_world",              lambda: scrape_ft_world()),
        ("news_stonex",                lambda: scrape_stonex()),
        ("news_tikr_blog",             lambda: scrape_tikr_blog()),
        ("news_yt_feer",               lambda: YTScraper(hours=24, channel="@fxevolutionvideo").scrape()),
        # ── analyst ────────────────────────────────────────────────────────────
        ("analyst_anachart_aapl",      lambda: scrape_anachart("aapl")),
        ("analyst_marketbeat_aapl",    lambda: scrape_marketbeat_forecast("AAPL", "NASDAQ")),
        # ── stock ──────────────────────────────────────────────────────────────
        ("stock_investing_aapl",       lambda: scrape_investing_stock("https://www.investing.com/equities/apple-computer-inc")),
        ("stock_yahoo_aapl",           lambda: scrape_yahoo_profile("AAPL")),
        # ── technical ──────────────────────────────────────────────────────────
        ("technical_market_overview",  lambda: scrape_market_overview()),
        ("technical_sentiment_outlook", lambda: scrape_sentiment_outlook()),
        # ── macro indicators ───────────────────────────────────────────────────
        ("indicator_vix",                    lambda: scrape_vix()),
        ("indicator_fear_greed",             lambda: scrape_fear_greed()),
        ("indicator_yield_curve",            lambda: scrape_yield_curve()),
        ("indicator_fed_funds_rate",         lambda: scrape_fed_funds_rate()),
        ("indicator_fed_june_probability",   lambda: scrape_fed_june_probability()),
        ("indicator_fed_balance_sheet",      lambda: scrape_fed_balance_sheet()),
        ("indicator_m2_us",                  lambda: scrape_m2_us()),
        ("indicator_global_m2",              lambda: scrape_global_m2()),
        ("indicator_rrp_facility",           lambda: scrape_rrp_facility()),
        ("indicator_margin_debt",            lambda: scrape_margin_debt()),
        ("indicator_spy_m2_ratio",           lambda: scrape_spy_m2_ratio()),
        ("indicator_breakeven_5y",           lambda: scrape_breakeven_5y()),
        ("indicator_breakeven_10y",          lambda: scrape_breakeven_10y()),
        ("indicator_core_pce",               lambda: scrape_core_pce()),
        ("indicator_ism_pmi",                lambda: scrape_ism_pmi()),
        ("indicator_shiller_cape",           lambda: scrape_shiller_cape()),
        ("indicator_buffett_indicator",      lambda: scrape_buffett_indicator()),
        ("indicator_equity_risk_premium",    lambda: scrape_equity_risk_premium()),
        ("indicator_lei",                    lambda: scrape_lei()),
        ("indicator_copper_gold_ratio",      lambda: scrape_copper_gold_ratio()),
        ("indicator_sp500_fwd_eps",          lambda: scrape_sp500_fwd_eps()),
        ("indicator_sp500_fwd_pe",           lambda: scrape_sp500_fwd_pe()),
        ("indicator_sp500_eps_growth",       lambda: scrape_sp500_eps_growth()),
        ("indicator_eurostoxx50_fwd_eps",    lambda: scrape_eurostoxx50_fwd_eps()),
        ("indicator_leading_sectors",        lambda: scrape_leading_sectors()),
    ]

    print("Running scrapers...")
    run_scrapers(SCRAPERS)
