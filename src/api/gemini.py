import time
from typing import Callable, TypeVar, Type

from google import genai
from google.genai import types
from google.genai.errors import ClientError
from pydantic import BaseModel

from src.config import GEMINI_API_KEY, GEMINI_API_KEY_FREE, GEMINI_MODEL

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

# Per-minute quota resets after ~60 s; retry free key after this window.
_FREE_RETRY_AFTER = 60.0


class _GeminiRouter:
    """Routes calls to the free-tier client first, falling back to paid on 429.

    The free tier is tied to a separate GCP project with its own quota.
    On RESOURCE_EXHAUSTED (429), the free client is marked unavailable for
    _FREE_RETRY_AFTER seconds before being tried again (RPM window reset).
    """

    def __init__(self) -> None:
        self._free = genai.Client(api_key=GEMINI_API_KEY_FREE) if GEMINI_API_KEY_FREE else None
        self._paid = genai.Client(api_key=GEMINI_API_KEY)
        self._free_exhausted_at: float = 0.0

    def _free_available(self) -> bool:
        return (
            self._free is not None
            and time.monotonic() - self._free_exhausted_at > _FREE_RETRY_AFTER
        )

    def call(self, fn: Callable[[genai.Client], T]) -> T:
        if self._free_available():
            try:
                return fn(self._free)  # type: ignore[arg-type]
            except ClientError as exc:
                if exc.code == 429:
                    self._free_exhausted_at = time.monotonic()
                else:
                    raise
        return fn(self._paid)


_router = _GeminiRouter()


def generate(prompt: str, model: str = GEMINI_MODEL) -> str:
    return _router.call(
        lambda client: client.models.generate_content(
            model=model, contents=prompt
        ).text
    )


def generate_with_search(prompt: str, model: str = GEMINI_MODEL) -> str:
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    return _router.call(
        lambda client: client.models.generate_content(
            model=model, contents=prompt, config=config
        ).text
    )


def generate_structured(prompt: str, schema: Type[M], model: str = GEMINI_MODEL) -> M:
    """Generate content and parse it into a Pydantic model.

    Uses response_schema to force the model to return valid JSON matching the schema.
    NOTE: Incompatible with Google Search grounding — use generate_with_search first
    to fetch fresh data, then pass the result here for structured extraction.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
    )
    raw = _router.call(
        lambda client: client.models.generate_content(
            model=model, contents=prompt, config=config
        ).text
    )
    return schema.model_validate_json(raw)


def search_then_extract(search_prompt: str, schema: Type[M], model: str = GEMINI_MODEL) -> M:
    """Two-step: web-grounded search → structured extraction.

    Step 1 — generate_with_search: retrieves fresh data from the web (no schema constraint).
    Step 2 — generate_structured: parses the raw text into a typed Pydantic model.

    Use this when you need both real-time web data AND reliable structured output.
    """
    raw_text = generate_with_search(search_prompt, model=model)
    extract_prompt = (
        "Extract the requested data from the following research text and return it "
        "as structured data matching the required schema. Use null for any value "
        "you cannot find with confidence.\n\n"
        f"Research text:\n{raw_text}"
    )
    return generate_structured(extract_prompt, schema, model=model)
