import time
from typing import Callable, TypeVar, Type

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError
from pydantic import BaseModel

from src.config import GEMINI_API_KEY, GEMINI_API_KEY_FREE, GEMINI_MODEL, GEMINI_MODEL_BACKUP

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

# Per-minute quota resets after ~60 s; retry free key after this window.
_FREE_RETRY_AFTER = 60.0

# Transient errors (503 model overloaded, 500, 429 on paid key): retry with
# backoff instead of bubbling the error text into the published report.
_RETRY_DELAYS = (15.0, 45.0, 90.0)
_RETRYABLE_CODES = {429, 500, 503}


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

    def _call_once(self, fn: Callable[[genai.Client], T]) -> T:
        if self._free_available():
            try:
                return fn(self._free)  # type: ignore[arg-type]
            except ClientError as exc:
                if exc.code == 429:
                    self._free_exhausted_at = time.monotonic()
                else:
                    raise
        return fn(self._paid)

    def call(self, fn: Callable[[genai.Client], T]) -> T:
        """Free→paid routing plus backoff on transient API errors (429/500/503)."""
        last_exc: APIError | None = None
        for attempt, delay in enumerate((0.0,) + _RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                return self._call_once(fn)
            except APIError as exc:
                if exc.code not in _RETRYABLE_CODES:
                    raise
                last_exc = exc
                print(f"  [gemini] transient {exc.code} (attempt {attempt + 1}/{1 + len(_RETRY_DELAYS)})")
        assert last_exc is not None
        raise last_exc


_router = _GeminiRouter()


def generate(prompt: str, model: str = GEMINI_MODEL) -> str:
    return _router.call(
        lambda client: client.models.generate_content(
            model=model, contents=prompt
        ).text
    )


def generate_lite(prompt: str) -> str:
    """Cheap-model variant for low-stakes tasks (transcript summaries, company
    blurbs, structured extraction). Falls back to the main model if the lite
    model errors out, so callers never lose output to save pennies."""
    try:
        return generate(prompt, model=GEMINI_MODEL_BACKUP)
    except APIError as exc:
        print(f"  [gemini] lite model failed ({exc.code}), falling back to {GEMINI_MODEL}")
        return generate(prompt)


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
            Extraction from already-fetched text is mechanical, so it runs on the
            cheaper lite model (with fallback to `model` on failure).

    Use this when you need both real-time web data AND reliable structured output.
    """
    raw_text = generate_with_search(search_prompt, model=model)
    extract_prompt = (
        "Extract the requested data from the following research text and return it "
        "as structured data matching the required schema. Use null for any value "
        "you cannot find with confidence.\n\n"
        f"Research text:\n{raw_text}"
    )
    try:
        return generate_structured(extract_prompt, schema, model=GEMINI_MODEL_BACKUP)
    except Exception:
        return generate_structured(extract_prompt, schema, model=model)
