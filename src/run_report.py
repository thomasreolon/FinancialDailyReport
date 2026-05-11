"""
Run the build_report pipeline and upload the result to Google Cloud Storage.

GCS paths written:
    reports/daily_report_YYYY-MM-DD.json   (date-stamped archive)
    reports/latest.json                     (always the most recent)

Bucket: the-mind-financial-reports
  Create once with:  gcloud storage buckets create gs://the-mind-financial-reports --location=EU

Usage:
    python src/run_report.py
    python src/run_report.py --force   # ignore today's checkpoints and re-run all stages
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

_BUCKET = "the-mind-financial-reports"
_PREFIX = "reports"
_LOCAL_OUT = ROOT / "output" / "pipeline" / "daily_report.json"


def _upload(json_str: str, date_str: str) -> None:
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(_BUCKET)

    for blob_name in (
        f"{_PREFIX}/daily_report_{date_str}.json",
        f"{_PREFIX}/latest.json",
    ):
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            json_str,
            content_type="application/json; charset=utf-8",
        )
        print(f"  uploaded → gs://{_BUCKET}/{blob_name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the daily market report pipeline and upload to GCS.")
    parser.add_argument("--force", action="store_true", help="Ignore today's checkpoints and re-run all stages.")
    parser.add_argument("--no-upload", action="store_true", help="Skip GCS upload (local run only).")
    args = parser.parse_args()

    print("=== The Market Ledger — Daily Report ===")
    print(f"Run started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    from src.pipelines.build_report import run_pipeline
    report = run_pipeline(force=args.force)

    json_str = report.model_dump_json(indent=2)

    _LOCAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    _LOCAL_OUT.write_text(json_str)
    print(f"\n  saved locally → {_LOCAL_OUT.relative_to(ROOT)}")

    if not args.no_upload:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        print("\nUploading to Google Cloud Storage...")
        _upload(json_str, date_str)

    print("\nDone.")


if __name__ == "__main__":
    main()
