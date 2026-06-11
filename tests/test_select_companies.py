"""Tests for top-3 company selection and NN score adjustment."""

from __future__ import annotations

import pytest

from src.ml.predictor import compute_nn_score
from src.pipelines.build_report.select_companies import (
    combined_score,
    companies_nn_sentiment,
    heuristic_score,
    select_top_companies,
)
from src.pipelines.screened_stocks import PipelineResult, ScreenedCompany, is_liquid_ticker
from tests.test_ml_features import _make_yahoo


def _company(
    ticker: str,
    *,
    nn: float | None = None,
    preds: dict[str, float] | None = None,
    cap: float | None = 1_000_000_000.0,
    sources: list[str] | None = None,
) -> ScreenedCompany:
    return ScreenedCompany(
        ticker=ticker,
        sources=sources or [],
        yahoo=_make_yahoo(symbol=ticker, income_annual=[], pe_ratio=None, market_cap=cap),
        anachart=None,
        marketbeat=None,
        nn_score=nn,
        nn_predictions=preds,
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


@pytest.mark.parametrize(
    "preds_1y,expected",
    [
        ([-10.0, -8.0, 1.0], "BEARISH"),             # pos_share 1/3 ≤ 0.35
        ([3.0, 4.0, -6.0, -7.0, -8.0], "BEARISH"),   # median -6 ≤ -5
        ([5.0, 6.0, -1.0, -2.0], "NEUTRAL"),         # pos_share 0.5 < 0.55
        ([5.0, 6.0, 7.0, -1.0], "BULLISH"),          # pos_share 0.75, median 6
        ([], "NEUTRAL"),
    ],
)
def test_companies_nn_sentiment_breadth(preds_1y, expected):
    companies = [
        _company(f"T{i}", preds={"return_1y_pct": p}) for i, p in enumerate(preds_1y)
    ]
    assert companies_nn_sentiment(companies) == expected


def test_companies_nn_sentiment_ignores_unscored():
    companies = [_company("AAA"), _company("BBB")]  # no nn_predictions
    assert companies_nn_sentiment(companies) == "NEUTRAL"


# ── liquidity guard ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "ticker,cap,expected",
    [
        ("AYALY", 5e9, False),   # OTC foreign ADR (…Y)
        ("AGGZF", 5e9, False),   # OTC foreign ADR (…F)
        ("AAPL", 100e6, False),  # sub-$500M cap
        ("AAPL", None, False),   # unknown cap
        ("AAPL", 1e9, True),
        ("GOOGL", 5e9, True),    # 5 letters but does not end in F/Y
    ],
)
def test_is_liquid_ticker(ticker, cap, expected):
    assert is_liquid_ticker(ticker, cap) is expected


def test_select_top_companies_skips_illiquid():
    liquid = [_company(t, nn=10.0) for t in ("AAA", "BBB", "CCC")]
    otc = _company("AYALY", nn=99.0, cap=5e9)
    small = _company("DDD", nn=50.0, cap=100e6)
    result = PipelineResult(companies=liquid + [otc, small], total=5)
    picks = select_top_companies(result, n=3)
    assert sorted(p.ticker for p in picks) == ["AAA", "BBB", "CCC"]


def test_select_top_companies_falls_back_when_too_few_liquid():
    companies = [_company("AYALY", nn=1.0, cap=5e9), _company("EEE", nn=2.0, cap=100e6)]
    result = PipelineResult(companies=companies, total=2)
    picks = select_top_companies(result, n=3)
    assert len(picks) == 2  # illiquid pool used rather than returning fewer
