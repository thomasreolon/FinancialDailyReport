"""Unit tests for src/ml/features.py — build_feature_vector + helpers.

Hand-rolled YahooProfile / MacroSnapshot instances exercise: FX conversion for
each supported currency, P/E clip + availability flag, macro composite bounds,
trend regression on oldest-first sorted statements, point-in-time ratios with
their training-time clamps, and the 76-element ordering against the model's
declared feature_names.
"""

from __future__ import annotations

import math

import pytest

from src.ml.features import (
    EXPECTED_FEATURE_NAMES,
    _mcap_to_eur,
    _ols_m_c,
    _period_year,
    _trend_pair,
    build_feature_vector,
)
from src.scrapers.stock.yahoo import (
    BalanceSheet,
    CashFlowStatement,
    IncomeStatement,
    YahooProfile,
)
from src.scrapers.technical.macro_snapshot import MacroSnapshot


# ── helpers to build minimal valid YahooProfile / MacroSnapshot ──────────────

def _make_snap(**overrides) -> MacroSnapshot:
    defaults = dict(
        vix=20.0,
        dgs10=4.0,
        dgs2=4.5,
        t10y2y=-0.5,
        hy_spread=3.2,
        usd_eur=1.08,
        usd_gbp=1.27,
        jpy_usd=150.0,
        sp500_ret_5d=0.5, sp500_ret_21d=1.0, sp500_ret_126d=4.0, sp500_ret_378d=10.0,
        wti_ret_5d=-1.0, wti_ret_21d=-2.0, wti_ret_126d=5.0, wti_ret_378d=15.0,
    )
    for tag in ("gld", "dbc", "dba", "cper", "lit", "weat"):
        for suf in ("5d", "21d", "126d", "378d"):
            defaults[f"etf_{tag}_ret_{suf}"] = 0.0
    defaults.update(overrides)
    return MacroSnapshot(**defaults)


def _make_yahoo(**overrides) -> YahooProfile:
    income = [
        IncomeStatement(
            period="2023-12-31",
            total_revenue=1_200.0,
            cost_of_revenue=600.0,
            gross_profit=600.0,
            research_development=None,
            sga=None,
            operating_income=200.0,
            ebit=None,
            interest_expense=None,
            net_income=120.0,
            diluted_eps=None,
        ),
        IncomeStatement(
            period="2022-12-31",
            total_revenue=1_100.0, cost_of_revenue=None, gross_profit=None,
            research_development=None, sga=None, operating_income=None, ebit=None,
            interest_expense=None, net_income=110.0, diluted_eps=None,
        ),
        IncomeStatement(
            period="2021-12-31",
            total_revenue=1_000.0, cost_of_revenue=None, gross_profit=None,
            research_development=None, sga=None, operating_income=None, ebit=None,
            interest_expense=None, net_income=100.0, diluted_eps=None,
        ),
    ]
    balance = [
        BalanceSheet(
            period="2023-12-31",
            total_assets=5_000.0, total_liabilities=None, total_equity=None,
            total_debt=None, net_debt=None, working_capital=None,
            invested_capital=None, shares_issued=None,
        ),
        BalanceSheet(
            period="2022-12-31",
            total_assets=4_500.0, total_liabilities=None, total_equity=None,
            total_debt=None, net_debt=None, working_capital=None,
            invested_capital=None, shares_issued=None,
        ),
        BalanceSheet(
            period="2021-12-31",
            total_assets=4_000.0, total_liabilities=None, total_equity=None,
            total_debt=None, net_debt=None, working_capital=None,
            invested_capital=None, shares_issued=None,
        ),
    ]
    defaults = dict(
        symbol="TEST", name="Test Co", exchange="NasdaqGS", currency="USD",
        sector=None, industry=None, description=None, employees=None, website=None,
        price=100.0, change_pct=None, market_cap=1_000_000_000.0,
        volume=None, avg_volume=None, week_52_high=None, week_52_low=None, beta=None,
        pe_ratio=18.0, forward_pe=None, peg_ratio=None, eps=None,
        dividend_yield_pct=None, enterprise_value=None, ev_revenue=None, ev_ebitda=None,
        profit_margin_pct=None, operating_margin_pct=None,
        return_on_equity_pct=None, return_on_assets_pct=None, gross_margin_pct=None,
        revenue=1_200.0, ebitda=None, net_income=120.0, free_cash_flow=None,
        total_cash=None, total_debt=None,
        short_ratio=None, short_pct_of_float=None, insider_pct=None,
        institution_pct=None, shares_outstanding=None,
        income_annual=income, income_quarterly=[],
        balance_annual=balance, balance_quarterly=[],
        cashflow_annual=[], cashflow_quarterly=[],
        earnings_estimates=[], earnings_history=[], recommendation_trend=[],
        ret_1d_pct=0.5, ret_5d_pct=1.0, ret_21d_pct=2.0, ret_42d_pct=4.0,
        ret_126d_pct=8.0, ret_252d_pct=15.0,
        vol_21d_pct=25.0,
        price_norm_d0=1.05, price_norm_d1=1.04, price_norm_d2=1.03, price_norm_d3=1.02,
        price_norm_d4=1.01, price_norm_d5=1.00, price_norm_d6=0.99, price_norm_d7=0.98,
        price_norm_d8=0.97, price_norm_d9=0.96,
        years_listed=12.5, first_trade_date="2011-01-01",
    )
    defaults.update(overrides)
    return YahooProfile(**defaults)


# ── _mcap_to_eur ─────────────────────────────────────────────────────────────

def test_mcap_eur_passthrough():
    assert _mcap_to_eur(1_000_000.0, "EUR", _make_snap()) == 1_000_000.0


def test_mcap_usd_to_eur():
    snap = _make_snap(usd_eur=1.08)
    # 1B USD / 1.08 = ~926M EUR
    assert abs(_mcap_to_eur(1e9, "USD", snap) - 1e9 / 1.08) < 1.0


def test_mcap_gbp_to_eur():
    snap = _make_snap(usd_eur=1.08, usd_gbp=1.27)
    expected = 1e9 * 1.27 / 1.08
    assert abs(_mcap_to_eur(1e9, "GBP", snap) - expected) < 1.0


def test_mcap_gbx_to_eur():
    """GBX = pence = GBP / 100."""
    snap = _make_snap(usd_eur=1.08, usd_gbp=1.27)
    expected = (1e9 / 100.0) * 1.27 / 1.08
    assert abs(_mcap_to_eur(1e9, "GBX", snap) - expected) < 1.0


def test_mcap_jpy_to_eur():
    snap = _make_snap(usd_eur=1.08, jpy_usd=150.0)
    expected = (1e9 / 150.0) / 1.08
    assert abs(_mcap_to_eur(1e9, "JPY", snap) - expected) < 1.0


def test_mcap_missing_fx_returns_none():
    snap = _make_snap(usd_eur=None)
    assert _mcap_to_eur(1e9, "USD", snap) is None


def test_mcap_unsupported_currency():
    assert _mcap_to_eur(1e9, "CHF", _make_snap()) is None


def test_mcap_zero_or_negative():
    assert _mcap_to_eur(0.0, "USD", _make_snap()) is None
    assert _mcap_to_eur(-1.0, "USD", _make_snap()) is None


# ── _ols_m_c ──────────────────────────────────────────────────────────────────

def test_ols_basic():
    # y = 2x + 1 perfectly
    m, c = _ols_m_c([0.0, 1.0, 2.0, 3.0], [1.0, 3.0, 5.0, 7.0])
    assert abs(m - 2.0) < 1e-9
    assert abs(c - 1.0) < 1e-9


def test_ols_zero_variance():
    m, c = _ols_m_c([1.0, 1.0, 1.0], [5.0, 5.0, 5.0])
    assert m == 0.0
    assert c == 5.0


# ── _period_year ──────────────────────────────────────────────────────────────

def test_period_year_parses_iso():
    assert _period_year("2023-12-31") == 2023


def test_period_year_handles_invalid():
    assert _period_year(None) is None
    assert _period_year("") is None
    assert _period_year("abcd") is None


# ── _trend_pair ──────────────────────────────────────────────────────────────

def test_trend_pair_growing_series():
    inc = [
        IncomeStatement(period="2021-12-31", total_revenue=1000.0, net_income=100.0,
                        cost_of_revenue=None, gross_profit=None, research_development=None,
                        sga=None, operating_income=None, ebit=None, interest_expense=None,
                        diluted_eps=None),
        IncomeStatement(period="2022-12-31", total_revenue=1100.0, net_income=110.0,
                        cost_of_revenue=None, gross_profit=None, research_development=None,
                        sga=None, operating_income=None, ebit=None, interest_expense=None,
                        diluted_eps=None),
        IncomeStatement(period="2023-12-31", total_revenue=1200.0, net_income=120.0,
                        cost_of_revenue=None, gross_profit=None, research_development=None,
                        sga=None, operating_income=None, ebit=None, interest_expense=None,
                        diluted_eps=None),
    ]
    bal = [
        BalanceSheet(period="2021-12-31", total_assets=4000.0, total_liabilities=None,
                     total_equity=None, total_debt=None, net_debt=None,
                     working_capital=None, invested_capital=None, shares_issued=None),
        BalanceSheet(period="2022-12-31", total_assets=4500.0, total_liabilities=None,
                     total_equity=None, total_debt=None, net_debt=None,
                     working_capital=None, invested_capital=None, shares_issued=None),
        BalanceSheet(period="2023-12-31", total_assets=5000.0, total_liabilities=None,
                     total_equity=None, total_debt=None, net_debt=None,
                     working_capital=None, invested_capital=None, shares_issued=None),
    ]
    # net_income slope = 10/yr, ta0 = 4000 → slope_norm = 10/4000 = 0.0025
    slope, icept, flag = _trend_pair(inc, bal, "net_income", mcap_eur=1e9)
    assert flag == 0.0
    assert abs(slope - 10.0 / 4000.0) < 1e-9


def test_trend_pair_too_few_points_flag():
    inc = [
        IncomeStatement(period="2023-12-31", total_revenue=1000.0, net_income=100.0,
                        cost_of_revenue=None, gross_profit=None, research_development=None,
                        sga=None, operating_income=None, ebit=None, interest_expense=None,
                        diluted_eps=None),
    ]
    slope, icept, flag = _trend_pair(inc, [], "net_income", mcap_eur=1e9)
    assert flag == 1.0
    assert slope == 0.0 and icept == 0.0


# ── build_feature_vector ─────────────────────────────────────────────────────

def test_feature_vector_length_and_finite():
    vec = build_feature_vector(_make_yahoo(), _make_snap())
    assert vec is not None
    assert len(vec) == len(EXPECTED_FEATURE_NAMES) == 76
    assert all(math.isfinite(v) for v in vec)


def test_feature_vector_log_mcap_usd():
    snap = _make_snap(usd_eur=1.08)
    yahoo = _make_yahoo(currency="USD", market_cap=1e9)
    vec = build_feature_vector(yahoo, snap)
    eur_mcap = 1e9 / 1.08
    expected = math.log10(eur_mcap + 1.0)
    assert abs(vec[0] - expected) < 1e-6


def test_feature_vector_log_mcap_eur():
    snap = _make_snap()
    yahoo = _make_yahoo(currency="EUR", market_cap=1e9)
    vec = build_feature_vector(yahoo, snap)
    expected = math.log10(1e9 + 1.0)
    assert abs(vec[0] - expected) < 1e-6


def test_feature_vector_pe_clip_high():
    yahoo = _make_yahoo(pe_ratio=500.0)
    vec = build_feature_vector(yahoo, _make_snap())
    # pe_ratio_clip is index 1; pe_available is index 47
    assert vec[1] == 300.0
    assert vec[47] == 1.0


def test_feature_vector_pe_clip_low_and_negative():
    yahoo = _make_yahoo(pe_ratio=-50.0)
    vec = build_feature_vector(yahoo, _make_snap())
    assert vec[1] == -20.0
    assert vec[47] == 1.0


def test_feature_vector_pe_missing():
    yahoo = _make_yahoo(pe_ratio=None)
    vec = build_feature_vector(yahoo, _make_snap())
    assert vec[1] == 0.0
    assert vec[47] == 0.0


def test_feature_vector_macro_composite_bounds():
    # vix=80 (n=2.0), dgs10=10 (n=2.0) → 0.5*2 + 0.5*2 = 2.0
    snap = _make_snap(vix=80.0, dgs10=10.0)
    vec = build_feature_vector(_make_yahoo(), snap)
    assert abs(vec[9] - 2.0) < 1e-9
    # Now blow past the cap: vix=200 (n=5), dgs10=20 (n=4) → would be 4.5, capped at 3
    snap2 = _make_snap(vix=200.0, dgs10=20.0)
    vec2 = build_feature_vector(_make_yahoo(), snap2)
    assert vec2[9] == 3.0
    # And the lower bound: negative vix (impossible but defensive) shouldn't go below 0
    snap3 = _make_snap(vix=None, dgs10=None)
    vec3 = build_feature_vector(_make_yahoo(), snap3)
    assert vec3[9] == 0.0


def test_feature_vector_sector_features_are_zero():
    vec = build_feature_vector(_make_yahoo(), _make_snap())
    # indices 44, 45, 46 = ret_126d_vs_sector_pct, pe_vs_sector_ratio, vol_21d_vs_sector_pct
    assert vec[44] == 0.0
    assert vec[45] == 0.0
    assert vec[46] == 0.0


def test_feature_vector_trend_with_newest_first_annuals():
    """YahooProfile lists annual statements newest-first; build_feature_vector
    must reverse them before the OLS fit so the slope sign is positive for a
    growing series."""
    vec = build_feature_vector(_make_yahoo(), _make_snap())
    # trend_profit_4y_slope is at index 48; growing series → positive slope
    assert vec[48] > 0
    # trend_profit_4y_flag is at index 50; 3 valid annual points → flag=0
    assert vec[50] == 0.0


def test_feature_vector_ratios_clamped():
    """gross_margin clamp at 5.0 when ratio explodes."""
    crazy_income = [
        IncomeStatement(period="2023-12-31", total_revenue=1.0, gross_profit=1000.0,
                        operating_income=None, net_income=None, cost_of_revenue=None,
                        research_development=None, sga=None, ebit=None,
                        interest_expense=None, diluted_eps=None),
    ]
    yahoo = _make_yahoo(income_annual=crazy_income)
    vec = build_feature_vector(yahoo, _make_snap())
    # gross_margin is index 60
    assert vec[60] == 5.0


def test_feature_vector_returns_none_when_no_price_history():
    yahoo = _make_yahoo(ret_126d_pct=None, ret_252d_pct=None)
    assert build_feature_vector(yahoo, _make_snap()) is None


def test_feature_vector_order_matches_meta():
    """Cross-check the in-code EXPECTED_FEATURE_NAMES against models/meta.json."""
    import json
    from pathlib import Path
    meta = json.loads(
        (Path(__file__).resolve().parents[1] / "models" / "nn_torch_snapshot_returns.meta.json").read_text()
    )
    assert tuple(meta["feature_names"]) == EXPECTED_FEATURE_NAMES
