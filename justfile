# Build the test image and run all tests inside Docker (uses the free/paid Gemini API keys from .env)
run-tests:
    docker compose --profile test run run-tests

# Run all scrapers and save JSON samples to output_screeners/.
# To add a scraper: edit scripts/run_scrapers.py and append to SCRAPERS.
run-scrapers:
    PYTHONPATH=. uv run python scripts/run_scrapers.py
