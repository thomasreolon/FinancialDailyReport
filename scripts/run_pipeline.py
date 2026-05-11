"""
Run all pipelines and save results to output/pipeline/.

  screened_stocks.json    — enriched company profiles from all screeners
  news.json               — market news aggregation with Gemini summaries
  macro_indicators.json   — global macro / economic indicators snapshot
  daily_report.json       — assembled daily report (runs all upstream pipelines)

Usage:
    python scripts/run_pipeline.py                        # all pipelines
    python scripts/run_pipeline.py --only news
    python scripts/run_pipeline.py --only screened_stocks
    python scripts/run_pipeline.py --only macro_indicators
    python scripts/run_pipeline.py --only build_report
    python scripts/run_pipeline.py --limit 10             # cap screened_stocks tickers
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "output" / "pipeline"


def run_screened_stocks(limit: int | None) -> None:
    from src.pipelines.screened_stocks import run_pipeline
    print("\n── screened_stocks ──────────────────────────────────────")
    result = run_pipeline()
    out = OUTPUT_DIR / "screened_stocks.json"
    out.write_text(result.model_dump_json(indent=2))
    print(f"  {result.total} companies → {out.relative_to(ROOT)}")
    if result.failed_tickers:
        print(f"  {len(result.failed_tickers)} failed: {result.failed_tickers}")


def run_news() -> None:
    from src.pipelines.news import run_pipeline
    print("\n── news ─────────────────────────────────────────────────")
    result = run_pipeline()
    out = OUTPUT_DIR / "news.json"
    out.write_text(result.model_dump_json(indent=2))
    print(f"  saved → {out.relative_to(ROOT)}")


def run_macro_indicators() -> None:
    from src.pipelines.macro_indicators import run_pipeline
    print("\n── macro_indicators ─────────────────────────────────────")
    result = run_pipeline()
    out = OUTPUT_DIR / "macro_indicators.json"
    out.write_text(result.model_dump_json(indent=2))
    filled = len(result.gemini_filled)
    print(f"  saved → {out.relative_to(ROOT)}  (Gemini filled {filled} fields)")


def run_build_report(force: bool = False) -> None:
    import json
    from src.pipelines.build_report import run_pipeline
    print("\n── build_report ─────────────────────────────────────────")
    bundle = run_pipeline(force=force)
    combined = {
        "report": bundle.report.model_dump(),
        "macro_indicators": bundle.macro.model_dump() if hasattr(bundle.macro, "model_dump") else bundle.macro,
        "screened_stocks": bundle.screened.model_dump() if hasattr(bundle.screened, "model_dump") else bundle.screened,
        "news": bundle.news.model_dump() if hasattr(bundle.news, "model_dump") else bundle.news,
        "market_overview": bundle.overview.model_dump() if hasattr(bundle.overview, "model_dump") else bundle.overview,
    }
    out = OUTPUT_DIR / "daily_report.json"
    out.write_text(json.dumps(combined, indent=2, default=str))
    print(f"  saved → {out.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        choices=["screened_stocks", "news", "macro_indicators", "build_report"],
        help="Run only one pipeline (default: all)",
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap tickers for screened_stocks (default: all)")
    parser.add_argument("--force", action="store_true",
                        help="Ignore today's checkpoints and re-run all stages (build_report only)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.only == "build_report":
        run_build_report(force=args.force)
        return

    if args.only == "news" or args.only is None:
        run_news()
    if args.only == "screened_stocks" or args.only is None:
        run_screened_stocks(args.limit)
    if args.only == "macro_indicators" or args.only is None:
        run_macro_indicators()


if __name__ == "__main__":
    main()
