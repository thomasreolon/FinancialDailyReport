set dotenv-load

PROJECT  := "the-mind-financial-reports"
REGION   := "europe-west1"
REGISTRY := REGION + "-docker.pkg.dev/" + PROJECT + "/apps"
SA       := "report-job-sa@" + PROJECT + ".iam.gserviceaccount.com"

# ── Health checks ─────────────────────────────────────────────────────────────

# Run all scraper health checks (~5 min)
health:
    uv run python scripts/health_check.py

# Health check + full pipeline smoke test (costs ~1 Gemini call)
health-full:
    uv run python scripts/health_check.py --full

# Health check for a single category: indicator | news | screener | stock | technical
health-cat category:
    uv run python scripts/health_check.py --category {{category}}

# Health check + live production server check (freshness + section completeness)
health-live:
    uv run python scripts/health_check.py --live

# ── Docker image verification ─────────────────────────────────────────────────

# Build the report-server image locally and verify all imports load
check-server-image:
    docker build --target report-server -t report-server-local . \
      && docker run --rm report-server-local uv run python -c \
           "from report_server.main import app; print('✓ report-server imports OK')"

# ── Local dev ──────────────────────────────────────────────────────────────────

# Start the report server locally (http://localhost:8000)
server:
    docker compose up -d report-server
    @echo "Server → http://localhost:8000"

server-logs:
    docker compose logs -f report-server

server-rebuild:
    docker compose build report-server && docker compose up -d report-server

# Run the full pipeline locally (with checkpoints)
run:
    .venv/bin/python src/run_report.py

run-force:
    .venv/bin/python src/run_report.py --force

# Run all scrapers and save JSON samples to output/screener/
run-scrapers:
    PYTHONPATH=. uv run python scripts/run_scrapers.py

# Run all tests inside Docker
run-tests:
    docker compose --profile test run run-tests

# ── Cloud Run: server ──────────────────────────────────────────────────────────

# Build, push and deploy the report-server Cloud Run service
deploy-server:
    #!/usr/bin/env bash
    set -euo pipefail
    IMAGE="{{REGISTRY}}/report-server:latest"

    echo "▶ Building report-server image..."
    docker build --target report-server -t "$IMAGE" .
    docker push "$IMAGE"

    echo "▶ Deploying Cloud Run service..."
    gcloud run deploy report-server \
        --image="$IMAGE" \
        --region={{REGION}} \
        --platform=managed \
        --allow-unauthenticated \
        --min-instances=0 \
        --max-instances=1 \
        --cpu=1 \
        --memory=512Mi \
        --service-account="{{SA}}" \
        --project={{PROJECT}} \
        --quiet

    echo ""
    echo "✓ Service URL:"
    gcloud run services describe report-server \
        --region={{REGION}} --project={{PROJECT}} \
        --format='value(status.url)'

# ── Cloud Run: job ─────────────────────────────────────────────────────────────

# Build, push and deploy the report-job Cloud Run Job + daily scheduler
deploy-job:
    #!/usr/bin/env bash
    set -euo pipefail
    IMAGE="{{REGISTRY}}/report-job:latest"

    echo "▶ Building report-job image..."
    docker build --target job -t "$IMAGE" .
    docker push "$IMAGE"

    # Prune old image versions from Artifact Registry (keep only :latest)
    gcloud artifacts docker images list "{{REGISTRY}}/report-job" \
        --include-tags --format='value(version,tags)' \
        --project={{PROJECT}} 2>/dev/null \
      | awk '$2 !~ /(^|,)latest(,|$)/ {print $1}' \
      | while read -r digest; do
            [ -n "$digest" ] && gcloud artifacts docker images delete \
                "{{REGISTRY}}/report-job@${digest}" \
                --delete-tags --quiet --project={{PROJECT}} 2>/dev/null || true
        done

    JOB_ARGS=(
        --image="$IMAGE"
        --service-account="{{SA}}"
        --region={{REGION}}
        --memory=2Gi
        --cpu=2
        --max-retries=0
        --task-timeout=60m
        --set-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest,GEMINI_API_KEY_FREE=GEMINI_API_KEY_FREE:latest,SCRAPEDO_API_KEY=SCRAPEDO_API_KEY:latest"
        --project={{PROJECT}}
    )

    if gcloud run jobs describe report-job \
           --region={{REGION}} --project={{PROJECT}} &>/dev/null; then
        echo "▶ Updating Cloud Run Job..."
        gcloud run jobs update report-job "${JOB_ARGS[@]}"
    else
        echo "▶ Creating Cloud Run Job..."
        gcloud run jobs create report-job "${JOB_ARGS[@]}"
    fi

    # Scheduler: weekdays 09:15 Europe/Rome (market open + 15 min buffer)
    SCHED_SA="report-scheduler-sa@{{PROJECT}}.iam.gserviceaccount.com"
    JOB_URI="https://run.googleapis.com/v2/projects/{{PROJECT}}/locations/{{REGION}}/jobs/report-job:run"
    SCHED_ARGS=(
        --location={{REGION}}
        --schedule="15 9 * * 1-5"
        --time-zone="Europe/Rome"
        --uri="$JOB_URI"
        --http-method=POST
        --message-body="{}"
        --oauth-service-account-email="$SCHED_SA"
        --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
        --project={{PROJECT}}
    )
    if gcloud scheduler jobs describe trigger-report-job \
           --location={{REGION}} --project={{PROJECT}} &>/dev/null; then
        echo "▶ Updating Cloud Scheduler..."
        gcloud scheduler jobs update http trigger-report-job "${SCHED_ARGS[@]}"
    else
        echo "▶ Creating Cloud Scheduler (first time only)..."
        gcloud run jobs add-iam-policy-binding report-job \
            --region={{REGION}} \
            --member="serviceAccount:${SCHED_SA}" \
            --role="roles/run.invoker" \
            --project={{PROJECT}} >/dev/null
        gcloud scheduler jobs create http trigger-report-job "${SCHED_ARGS[@]}"
    fi

    echo ""
    echo "✓ Job deployed. Schedule: 09:15 Europe/Rome, Mon–Fri"
    echo "  Run now:  just run-job"

# ── Deploy both ────────────────────────────────────────────────────────────────

# Build and deploy server + job
deploy: deploy-server deploy-job

# ── GCP Logs ──────────────────────────────────────────────────────────────────

# Stream stdout/stderr from the last report-job execution (last 24h, chronological)
logs-job:
    gcloud logging read \
      'resource.type="cloud_run_job" AND resource.labels.job_name="report-job" AND logName=~"stdout|stderr"' \
      --project={{PROJECT}} \
      --limit=500 \
      --freshness=1d \
      --format='table(timestamp.date("%H:%M:%S"):label=TIME, textPayload:label=LOG)' \
      --order=asc

# Show report-server logs: HTTP requests + app stdout/stderr (last 24h)
logs-server:
    gcloud logging read \
      'resource.type="cloud_run_revision" AND resource.labels.service_name="report-server"' \
      --project={{PROJECT}} \
      --limit=200 \
      --freshness=1d \
      --format='table(timestamp.date("%H:%M:%S"):label=TIME, httpRequest.status:label=STATUS, httpRequest.requestMethod:label=METHOD, httpRequest.requestUrl.basename():label=PATH, textPayload:label=LOG)' \
      --order=asc

# ── Manual triggers ────────────────────────────────────────────────────────────

# Trigger the Cloud Run job immediately and tail its logs
run-job:
    gcloud run jobs execute report-job \
        --region={{REGION}} --project={{PROJECT}} --wait
