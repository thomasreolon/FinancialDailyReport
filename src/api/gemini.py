import time
from typing import Callable, TypeVar

from google import genai
from google.genai import types
from google.genai.errors import ClientError

from src.config import GEMINI_API_KEY, GEMINI_API_KEY_FREE, GEMINI_MODEL

T = TypeVar("T")

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
