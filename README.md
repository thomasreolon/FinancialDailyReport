# The Market Ledger 📊

A daily financial intelligence pipeline for US markets. Every weekday at 09:15 CET it scrapes macro indicators, news sources, and stock screeners, enriches the raw data with Gemini LLM analysis and Google Search grounding, and assembles a structured report served via a FastAPI server on GCP Cloud Run.

Screened tickers are scored with a bundled neural net (`models/nn_torch_snapshot_returns.joblib`) that predicts forward returns; the report highlights the top three picks and an overall companies sentiment (BULLISH / NEUTRAL / BEARISH). Benchmark quotes (SPY, VWCE) are included for context.

**Live report →** https://report-server-rz3teebbga-ew.a.run.app

---

## Usage

### Health checks

```bash
just health              # run all scraper checks (~5 min)
just health-live         # + live server freshness & completeness check
just health-full         # + macro pipeline smoke test + NN model check (~1 Gemini call)
just health-cat screener # single category: indicator | news | screener | stock | technical
```

### Local development

```bash
just server              # start report server at http://localhost:8000 (Docker)
just server-logs         # tail server logs
just run                 # run the full pipeline locally (resumes from checkpoints)
just run-force           # re-run all stages, ignoring checkpoints
```

### Logs (GCP)

```bash
just logs-job            # last 24h of Cloud Run job output
just logs-server         # last 24h of server request/error logs
```

### Deploy 🚀

Push to `main` — GitHub Actions builds the Docker image and deploys to Cloud Run automatically.

To deploy manually or update infrastructure:

```bash
just deploy              # build + deploy server and job
just deploy-server       # server only
just deploy-job          # job + Cloud Scheduler only
just run-job             # trigger the job immediately and tail logs
```

---

## Archived data (GCS)

Each run uploads `raw/YYYY-MM-DD.json` and `raw/latest.json` to the bucket `the-mind-financial-reports`. Besides the rendered `report`, the JSON keeps full pipeline payloads for backtesting and analysis:

| Key | Role |
|-----|------|
| `screened_stocks` | Every screened ticker with Yahoo / AnaChart / MarketBeat data, plus `nn_predictions` and `nn_score` |
| `macro_snapshot` | Macro levels and session-count returns shared by the NN feature builder |
| `macro_indicators`, `news`, `market_overview` | Other pipeline stages as scraped/enriched that day |

NN inputs are not stored as a fixed 76-feature vector, but you can **recompute them from the archive without re-scraping** (`yahoo` + `macro_snapshot` via `src/ml/features.py`). Maintainer notes (feature versioning, drift checks, screened-only universe) are in [CLAUDE.md](CLAUDE.md#nn-model-and-backtesting-from-archived-raw-data).
