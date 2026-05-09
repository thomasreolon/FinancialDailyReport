from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent.parent / ".env")


# Secrets
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
GEMINI_API_KEY_FREE: str | None = os.environ.get("GEMINI_API_KEY_FREE")
SCRAPEDO_API_KEY: str | None = os.environ.get("SCRAPEDO_API_KEY")

# GCP Configs
GEMINI_MODEL: str = "gemini-3-flash-preview"
GEMINI_MODEL_BACKUP: str = "gemini-3.1-flash-lite"



