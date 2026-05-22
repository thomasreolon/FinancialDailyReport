FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Chromium browser + all its system dependencies (libnss3, libgbm1, fonts, etc.)
# --with-deps runs apt-get internally for the exact libs the installed browser version needs
RUN uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# --- production image ---
FROM base AS prod
COPY src/ ./src/
ENV PYTHONPATH=/app
CMD ["python", "-m", "src"]

# --- report server (slim — only FastAPI + GCS, no scraping stack) ---
FROM python:3.12-slim AS report-server
WORKDIR /app
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --only-group server
COPY report_server/ ./report_server/
ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["sh", "-c", "uv run uvicorn report_server.main:app --host 0.0.0.0 --port ${PORT:-8080}"]

# --- pipeline job ---
FROM base AS job
COPY src/ ./src/
COPY models/ ./models/
COPY personal_view.md ./personal_view.md
ENV PYTHONPATH=/app
CMD ["uv", "run", "python", "src/run_report.py"]

# --- test image (adds pytest) ---
FROM base AS test
RUN uv sync --frozen
COPY src/ ./src/
COPY tests/ ./tests/
ENV PYTHONPATH=/app
CMD ["uv", "run", "pytest", "tests/", "-v"]
