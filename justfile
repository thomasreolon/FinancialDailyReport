# Build the test image and run all tests inside Docker (uses the free/paid Gemini API keys from .env)
run-tests:
    docker compose --profile test run run-tests
