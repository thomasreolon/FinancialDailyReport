FROM python:3.12-slim AS base

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./

# --- production image ---
FROM base AS prod
RUN uv sync --frozen --no-dev
COPY src/ ./src/
ENV PYTHONPATH=/app
CMD ["python", "-m", "src"]

# --- test image (includes pytest + tests/) ---
FROM base AS test
RUN uv sync --frozen --extra dev
COPY src/ ./src/
COPY tests/ ./tests/
ENV PYTHONPATH=/app
CMD ["uv", "run", "pytest", "tests/", "-v"]
