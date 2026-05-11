"""Per-IP sliding-window rate limiter (thread-safe, deque-based)."""
from __future__ import annotations

import time
from collections import deque
from threading import Lock

_WINDOW = 60.0   # seconds
_LIMIT = 60      # requests per window

_store: dict[str, deque[float]] = {}
_lock = Lock()


def is_allowed(ip: str) -> bool:
    now = time.monotonic()
    with _lock:
        dq = _store.setdefault(ip, deque())
        while dq and dq[0] < now - _WINDOW:
            dq.popleft()
        if len(dq) >= _LIMIT:
            return False
        dq.append(now)
        # Prune fully-idle entries to bound memory
        if len(_store) > 10_000:
            dead = [k for k, v in _store.items() if not v]
            for k in dead:
                del _store[k]
        return True
