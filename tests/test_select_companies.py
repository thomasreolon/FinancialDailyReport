"""Tests for top-3 company selection and NN score adjustment."""

from __future__ import annotations

import pytest

from src.ml.predictor import compute_nn_score
from src.pipelines.build_report.select_companies import (
    combined_score,
    heuristic_score,
    select_top_companies,
)
from src.pipelines.screened_stocks import PipelineResult, ScreenedCompany
from tests.test_ml_features import _make_yahoo


def _company(ticker: str, *, nn: float | None = None, sources: list[str] | None = None) -> ScreenedCompany:
    return ScreenedCompany(
        ticker=ticker,
        sources=sources or [],
        yahoo=_make_yahoo(symbol=ticker, income_annual=[], pe_ratio=None),
        anachart=None,
        marketbeat=None,
        nn_score=nn,
    )


def test_compute_nn_score_floor_for_small_positive():
    preds = {"return_1y_pct": 0.5, "return_3y_pct": 2.0}
    base = min(preds["return_1y_pct"] * 2.0, preds["return_3y_pct"])
    assert compute_nn_score(preds) == pytest.approx(max(0.01 + base / 100.0, base))


def test_compute_nn_score_keeps_large_values():
    preds = {"return_1y_pct": 40.0, "return_3y_pct": 80.0}
    assert compute_nn_score(preds) == 80.0


def test_select_top_three_uses_distinct_criteria():
    a = _company("AAA", nn=50.0, sources=["s1"])
    b = _company("BBB", nn=10.0, sources=["s1", "s2", "s3", "s4"])
    c = _company("CCC", nn=30.0, sources=["s1"])
    # B has stronger heuristic (4 screeners → +0.15) than A/C
    result = PipelineResult(companies=[a, b, c], total=3)
    picks = select_top_companies(result, n=3)
    assert [p.ticker for p in picks] == ["AAA", "BBB", "CCC"]


def test_combined_score_formula():
    c = _company("X", nn=30.0)
    h = heuristic_score(c)
    assert combined_score(c) == pytest.approx((30.0 + 0.3) / 1.2 + h / 2.0)
