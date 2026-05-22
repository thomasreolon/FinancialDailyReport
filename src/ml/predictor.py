"""Inference wrapper for the ff_analysis snapshot-returns NN model.

The bundle stores a sklearn ``Pipeline([("scaler", StandardScaler()), ("reg",
TorchMLPRegressor(...))])``. Joblib unpickle needs ``training_torch.mlp`` to be
importable — we add ``src/`` to ``sys.path`` once before the first load.

Model file (``models/nn_torch_snapshot_returns.joblib``) is loaded lazily on
first call and cached for the lifetime of the process.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import joblib
import numpy as np

from src.ml.features import EXPECTED_FEATURE_NAMES, build_feature_vector

if TYPE_CHECKING:
    from src.scrapers.stock.yahoo import YahooProfile
    from src.scrapers.technical.macro_snapshot import MacroSnapshot


_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "nn_torch_snapshot_returns.joblib"
_bundle: dict | None = None


def _load() -> dict:
    global _bundle
    if _bundle is None:
        # The joblib pickle references training_torch.mlp.TorchMLPRegressor —
        # make sure src/ is importable so the class resolves on unpickle.
        src_dir = Path(__file__).resolve().parents[1]
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        b = joblib.load(_MODEL_PATH)
        if list(b["feature_names"]) != list(EXPECTED_FEATURE_NAMES):
            raise RuntimeError(
                "Model feature_names drifted from src/ml/features.py EXPECTED_FEATURE_NAMES. "
                f"Bundle has {len(b['feature_names'])} features, code expects {len(EXPECTED_FEATURE_NAMES)}."
            )
        _bundle = b
    return _bundle


def predict(yahoo: "YahooProfile", snap: "MacroSnapshot") -> dict[str, float] | None:
    """Return {target_name: predicted_pct} or None when features can't be built."""
    vec = build_feature_vector(yahoo, snap)
    if vec is None:
        return None
    bundle = _load()
    x = np.asarray(vec, dtype=np.float64).reshape(1, -1)
    y = bundle["pipeline"].predict(x)[0]
    return dict(zip(bundle["target_names"], y.tolist()))


def compute_nn_score(preds: dict[str, float]) -> float:
    """Composite score used for ranking screened stocks.

    min(1y * 2, 3y) rewards companies whose 3y return matches or exceeds twice
    their 1y return — i.e. sustained growth, not just a near-term pop.
    """
    return min(preds["return_1y_pct"] * 2.0, preds["return_3y_pct"])
