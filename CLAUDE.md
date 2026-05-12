# The Market Ledger — AI Agent Guide

## What this project does

A daily financial intelligence pipeline that:
1. **Scrapes** macro indicators (FRED, Yahoo Finance, etc.), news (FT, StoneX, TIKR, YouTube), stock screeners, and analyst ratings
2. **Enriches** raw data with Gemini LLM analysis and Google Search grounding
3. **Assembles** a structured daily report and uploads it to Google Cloud Storage
4. **Serves** the report via a FastAPI server deployed on GCP Cloud Run

## Your weekly task

Run the health check, read the output, fix any broken scrapers, then push to deploy.

```bash
# Standard run — all scrapers, ~5 minutes
python scripts/health_check.py

# With pipeline smoke test — also runs macro_indicators end-to-end (costs ~1 Gemini API call)
python scripts/health_check.py --full

# Single category if you already know where the problem is
python scripts/health_check.py --category indicator
python scripts/health_check.py --category news
python scripts/health_check.py --category screener
python scripts/health_check.py --category stock
python scripts/health_check.py --category technical
```

The report is written to `output/health_YYYY-MM-DD.md`. Exit code 1 means at least one scraper FAILed.

---

## Project layout

```
src/
  scrapers/
    indicator/     # Macro indicators — one file per series (FRED, Yahoo, etc.)
    news/          # News sources (FT World, StoneX, TIKR blog, YouTube)
    screener/      # Stock screeners (Yahoo trending, PortfolioPilot, MarketBeat golden cross)
    stock/         # Individual stock profiles (Yahoo Finance)
    analyst/       # Analyst ratings (AnaChart, MarketBeat)
    technical/     # Market-wide ETF overview & sentiment outlook
    base.py        # ScrapingNode ABC (all scrapers inherit from this)
  pipelines/
    macro_indicators.py   # Runs all indicator scrapers + Gemini fills gaps
    news.py               # Runs all news scrapers + Gemini summarises
    screened_stocks.py    # Deduplicates tickers, enriches each with Yahoo/AnaChart/MarketBeat
    build_report/         # Assembles everything into a DailyReport Pydantic model
  api/
    gemini.py      # Gemini client — routes free key first, paid key on 429
    web_fetcher.py # 5-tier HTML fetcher: requests → curl_cffi → Playwright stealth → Playwright human → scrape.do
    youtube.py     # yt-dlp wrapper for fetching channel transcripts
  config.py        # Env var declarations (GEMINI_API_KEY, FRED_API_KEY, etc.)

report_server/     # FastAPI server — reads from GCS, serves rendered HTML report
scripts/
  health_check.py  # Your primary tool — runs every scraper with diagnostics
  run_pipeline.py  # Manually re-run specific pipeline stages (see below)
```

---

## Interpreting health check output

| Status | Meaning |
|--------|---------|
| ✅ OK | Scraper succeeded, data is in expected range, not stale |
| ⚠️ WARN | Scraper succeeded but something is off — read the warning message |
| ❌ FAIL | Scraper raised an exception or returned None unexpectedly |

**Common WARN messages:**

- `returned None — no data available right now` — expected for some scrapers (e.g., no YouTube video uploaded in the last 72h, or `fed_june_probability` which always delegates to Gemini). Not a problem.
- `data is Xd old (threshold: Yd)` — the scraper ran fine but the source data is stale. For monthly FRED series (M2, core PCE, LEI) a lag of 30–50 days is normal. For daily series (VIX, yield curve) this is a sign the scraper may be broken or the FRED API is not updating.
- Range warning (e.g., `PMI 99 out of [20, 70]`) — the value is implausible. The scraper likely parsed a wrong HTML element because the page structure changed.

**Common FAIL messages:**

- `ReadTimeoutError: fredgraph.csv unreachable` — FRED's CSV endpoint is blocked on cloud/GCP IPs. **Fix: ensure `FRED_API_KEY` is set in the environment** (free at https://fred.stlouisfed.org/docs/api/api_key.html). The `_fred.py` module uses the official JSON API when the key is available.
- `extract() failed — possible model field change` — the scraper's Pydantic result model changed and the health check's `Spec.extract` lambda references an old field name. Update the lambda in `scripts/health_check.py`.
- `KeyError / AttributeError / IndexError` in the traceback — the source website changed its HTML structure or JSON schema. Open the scraper file and compare the CSS selectors / JSON paths against the current live page.
- `All fetch tiers failed` — `web_fetcher.py` exhausted all 5 tiers (requests, curl_cffi, Playwright stealth, Playwright human, scrape.do). The site has very aggressive bot detection. Check if `SCRAPEDO_API_KEY` is set; if yes, the scrape.do tier ran but also failed — look at the HTTP status codes in the traceback.

---

## Fixing a broken scraper

### Step 1 — identify the scraper file

Each scraper lives in `src/scrapers/<category>/<name>.py`. The health check `name` field maps directly to the filename (e.g., `vix` → `src/scrapers/indicator/vix.py`).

### Step 2 — test it in isolation

```bash
# Quick REPL test
python -c "from src.scrapers.indicator.vix import scrape_vix; print(scrape_vix())"

# Or for a scraper that needs a ticker
python -c "from src.scrapers.stock.yahoo import scrape_yahoo_profile; print(scrape_yahoo_profile('AAPL'))"
```

### Step 3 — inspect the live page

For HTML scrapers, print the raw HTML to see what the site currently returns:

```bash
python -c "
from src.api.web_fetcher import fetch_html
html = fetch_html('https://example.com/page')
print(html[:3000])
"
```

Compare against the CSS selectors or JSON paths in the scraper. Update selectors as needed.

### Step 4 — validate the fix

```bash
python scripts/health_check.py --category <category>
```

### Step 5 — deploy

Push to `main`. GitHub Actions automatically deploys to GCP Cloud Run. No manual step needed.

```bash
git add src/scrapers/...
git commit -m "fix: update <scraper_name> selector for new site structure"
git push
```

---

## Adding Gemini as a fallback for a failing scraper

If a scraper for a macro indicator is permanently broken (site is dead, requires login, etc.), add its field to `_GeminiFill` in `src/pipelines/macro_indicators.py`. Gemini with Google Search grounding will fill it from web data. See the existing entries for the pattern — each field needs a clear `description` in the Field definition.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | ✅ | Google Gemini API key (paid tier) |
| `GEMINI_API_KEY_FREE` | optional | Secondary free-tier key — used first to reduce costs |
| `FRED_API_KEY` | ✅ | FRED API key — free at fred.stlouisfed.org. Without this, all FRED-based indicators fail on cloud IPs |
| `SCRAPEDO_API_KEY` | optional | scrape.do residential proxy API — last-resort tier in `web_fetcher.py` |

---

## Manually re-running pipeline stages

```bash
python src/run_report.py                 # full pipeline + upload to GCS
python src/run_report.py --no-upload     # full pipeline, save locally only
python src/run_report.py --force         # ignore today's checkpoints, re-run all stages

python scripts/run_pipeline.py --only news
python scripts/run_pipeline.py --only macro_indicators
python scripts/run_pipeline.py --only screened_stocks
python scripts/run_pipeline.py --only build_report
python scripts/run_pipeline.py --only build_report --force
```

Checkpoints are pickled to `/tmp/ee_mind_report_YYYY-MM-DD/` so a crashed run can resume without re-scraping. Use `--force` to bypass them.

---

## Deployment

**All deploys are automatic** — push to `main` and GitHub Actions handles the rest. The action builds the Docker image and updates the GCP Cloud Run service. Check the Actions tab if the service seems down after a push.

The GCS bucket `the-mind-financial-reports` stores reports as `raw/YYYY-MM-DD.json` and `raw/latest.json`. The report server reads from GCS with a 5-minute TTL cache for recent dates.
