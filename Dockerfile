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

# --- report server ---
FROM base AS report-server
COPY src/ ./src/
COPY report_server/ ./report_server/
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "report_server.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- test image (adds pytest) ---
FROM base AS test
RUN uv sync --frozen --extra dev
COPY src/ ./src/
COPY tests/ ./tests/
ENV PYTHONPATH=/app
CMD ["uv", "run", "pytest", "tests/", "-v"]
