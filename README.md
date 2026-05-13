# The Market Ledger 📊

A daily financial intelligence pipeline for US markets. Every weekday at 09:15 CET it scrapes macro indicators, news sources, and stock screeners, enriches the raw data with Gemini LLM analysis and Google Search grounding, and assembles a structured report served via a FastAPI server on GCP Cloud Run.

**Live report →** https://report-server-rz3teebbga-ew.a.run.app

---

## Usage

### Health checks

```bash
just health              # run all scraper checks (~5 min)
just health-live         # + live server freshness & completeness check
just health-full         # + macro pipeline smoke test (~1 Gemini call)
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
