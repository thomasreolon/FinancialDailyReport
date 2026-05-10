"""
Run all registered scrapers and save results to output_screeners/.

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

OUTPUT_DIR = ROOT / "output_screeners"


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
    from src.scrapers.investing_stock import scrape_investing_stock
    from src.scrapers.yt_scraper import YTScraper
    from src.scrapers.screener.investing import scrape_mid_cap_losers
    from src.scrapers.screener.yahoo_trending import scrape_yahoo_trending
    from src.scrapers.screener.portfoliopilot import scrape_portfoliopilot
    from src.scrapers.screener.marketbeat_golden_cross import scrape_golden_cross
    from src.scrapers.news.ft_world import scrape_ft_world
    from src.scrapers.news.stonex import scrape_stonex
    from src.scrapers.news.tikr_blog import scrape_tikr_blog
    from src.scrapers.analyst.anachart import scrape_anachart
    from src.scrapers.analyst.marketbeat import scrape_marketbeat_forecast

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
        # ── analyst ────────────────────────────────────────────────────────────
        ("analyst_anachart_aapl",      lambda: scrape_anachart("aapl")),
        ("analyst_marketbeat_aapl",    lambda: scrape_marketbeat_forecast("AAPL", "NASDAQ")),
        # ── legacy ─────────────────────────────────────────────────────────────
        ("investing_stock_aapl",       lambda: scrape_investing_stock("https://www.investing.com/equities/apple-computer-inc")),
        ("yt_scraper",                 lambda: YTScraper(hours=24, channel="@Feer").scrape()),
    ]

    print("Running scrapers...")
    run_scrapers(SCRAPERS)
