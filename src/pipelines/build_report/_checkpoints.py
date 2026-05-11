"""
Pickle-based checkpoints saved to /tmp/ee_mind_report_<date>/.

Each upstream pipeline result is cached by name for the current calendar day.
On resume after a crash, completed stages are loaded from disk instead of re-run.
"""

from __future__ import annotations

import pickle
from datetime import date
from pathlib import Path

_BASE = Path("/tmp") / f"ee_mind_report_{date.today().isoformat()}"


def _path(name: str) -> Path:
    _BASE.mkdir(parents=True, exist_ok=True)
    return _BASE / f"{name}.pkl"


def save(name: str, obj: object) -> None:
    _path(name).write_bytes(pickle.dumps(obj))


def load(name: str) -> object | None:
    p = _path(name)
    if p.exists():
        return pickle.loads(p.read_bytes())
    return None


def exists(name: str) -> bool:
    return _path(name).exists()


def clear_all() -> None:
    """Remove all checkpoints for today (force full re-run)."""
    if _BASE.exists():
        for f in _BASE.glob("*.pkl"):
            f.unlink()
