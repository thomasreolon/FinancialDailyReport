"""
Run the screened-stocks pipeline and save the result to output/pipeline/screened_stocks.json.

Usage:
    python scripts/run_pipeline.py          # all tickers (slow — one Playwright session per ticker)
    python scripts/run_pipeline.py --limit 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.pipelines.screened_stocks import run_pipeline

OUTPUT_DIR = ROOT / "output" / "pipeline"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of tickers to process (default: all)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Running screened-stocks pipeline...")
    result = run_pipeline()

    out_path = OUTPUT_DIR / "screened_stocks.json"
    out_path.write_text(result.model_dump_json(indent=2))

    print(f"\n  {result.total} companies saved → {out_path.relative_to(ROOT)}")
    if result.failed_tickers:
        print(f"  {len(result.failed_tickers)} failed: {result.failed_tickers}")


if __name__ == "__main__":
    main()
