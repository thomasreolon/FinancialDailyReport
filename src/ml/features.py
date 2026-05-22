"""Feature assembly for the ff_analysis snapshot-returns NN model.

`build_feature_vector` takes a `YahooProfile` + `MacroSnapshot` (the ones already
produced by the existing pipeline) and returns the 76-element feature vector in
the exact order the trained model expects (see
``models/nn_torch_snapshot_returns.meta.json``).

Mirrors the training-time pipeline in
``ff_analysis/src/features/snapshot_features.py``:

  - Market cap is converted to EUR via the same FX helper (EUR/USD/GBP/GBX/JPY).
  - P/E is clipped to [-20, 300]; 0.0 when missing (the `pe_available` flag
    lets the model distinguish missing from low).
  - Annual income/balance statements are sorted oldest→newest before the OLS
    trend fits, matching training.
  - Margin / ratio / trend features carry the same clamps as training.
  - Sector-relative features are hard-zero (we have no sector medians cache).
  - Missing scalar features fall back to 0.0 (same as training).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.scrapers.stock.yahoo import IncomeStatement, BalanceSheet, YahooProfile
    from src.scrapers.technical.macro_snapshot import MacroSnapshot


# Order matches models/nn_torch_snapshot_returns.meta.json feature_names.
EXPECTED_FEATURE_NAMES: tuple[str, ...] = (
    "log10_mcap_eur_plus1",
    "pe_ratio_clip",
    "ret_1d_pct", "ret_5d_pct", "ret_21d_pct", "ret_42d_pct", "ret_126d_pct", "ret_252d_pct",
    "vol_21d_pct",
    "macro_composite_vix_dgs10",
    "sp500_ret_5d_pct", "sp500_ret_21d_pct", "sp500_ret_126d_pct", "sp500_ret_378d_pct",
    "wti_ret_5d_pct", "wti_ret_21d_pct", "wti_ret_126d_pct", "wti_ret_378d_pct",
    "hy_spread_pct", "yield_curve_t10y2y_pct",
    "etf_gld_ret_5d_pct", "etf_gld_ret_21d_pct", "etf_gld_ret_126d_pct", "etf_gld_ret_378d_pct",
    "etf_dbc_ret_5d_pct", "etf_dbc_ret_21d_pct", "etf_dbc_ret_126d_pct", "etf_dbc_ret_378d_pct",
    "etf_dba_ret_5d_pct", "etf_dba_ret_21d_pct", "etf_dba_ret_126d_pct", "etf_dba_ret_378d_pct",
    "etf_cper_ret_5d_pct", "etf_cper_ret_21d_pct", "etf_cper_ret_126d_pct", "etf_cper_ret_378d_pct",
    "etf_lit_ret_5d_pct", "etf_lit_ret_21d_pct", "etf_lit_ret_126d_pct", "etf_lit_ret_378d_pct",
    "etf_weat_ret_5d_pct", "etf_weat_ret_21d_pct", "etf_weat_ret_126d_pct", "etf_weat_ret_378d_pct",
    "ret_126d_vs_sector_pct", "pe_vs_sector_ratio", "vol_21d_vs_sector_pct",
    "pe_available",
    "trend_profit_4y_slope", "trend_profit_4y_intercept", "trend_profit_4y_flag",
    "trend_profit_all_slope", "trend_profit_all_intercept", "trend_profit_all_flag",
    "trend_revenue_4y_slope", "trend_revenue_4y_intercept", "trend_revenue_4y_flag",
    "trend_revenue_all_slope", "trend_revenue_all_intercept", "trend_revenue_all_flag",
    "gross_margin", "operating_margin", "price_to_sales", "asset_turnover",
    "earnings_recency", "years_listed",
    "price_norm_d0", "price_norm_d1", "price_norm_d2", "price_norm_d3", "price_norm_d4",
    "price_norm_d5", "price_norm_d6", "price_norm_d7", "price_norm_d8", "price_norm_d9",
)
assert len(EXPECTED_FEATURE_NAMES) == 76


PE_RATIO_CLIP_LO = -20.0
PE_RATIO_CLIP_HI = 300.0


# ── FX: native market cap → EUR ──────────────────────────────────────────────

def _mcap_to_eur(market_cap_native: float | None, currency: str | None, snap: "MacroSnapshot") -> float | None:
    """Convert market cap from native reporting currency to EUR.

    Returns None when the currency isn't supported (EUR/USD/GBP/GBX/JPY) or the
    relevant FX rate is missing — caller should map None → log10 = 0.0.
    """
    if market_cap_native is None or market_cap_native <= 0:
        return None
    ccy = (currency or "").upper()
    if ccy == "EUR":
        return float(market_cap_native)
    if not snap.usd_eur or snap.usd_eur <= 0:
        return None
    usd_per_eur = float(snap.usd_eur)  # e.g. 1.08 → 1 EUR = 1.08 USD
    if ccy == "USD":
        return float(market_cap_native) / usd_per_eur
    if ccy in ("GBP", "GBX"):
        if not snap.usd_gbp or snap.usd_gbp <= 0:
            return None
        gbp_amount = float(market_cap_native) / 100.0 if ccy == "GBX" else float(market_cap_native)
        return gbp_amount * float(snap.usd_gbp) / usd_per_eur
    if ccy == "JPY":
        if not snap.jpy_usd or snap.jpy_usd <= 0:
            return None
        return (float(market_cap_native) / float(snap.jpy_usd)) / usd_per_eur
    return None


# ── OLS trend on annual statements ───────────────────────────────────────────

def _ols_m_c(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    if ss_xx == 0:
        return 0.0, mean_y
    m = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / ss_xx
    return m, mean_y - m * mean_x


def _period_year(period: str | None) -> int | None:
    if not period or len(period) < 4:
        return None
    try:
        return int(period[:4])
    except ValueError:
        return None


def _trend_pair(
    inc_window: list["IncomeStatement"],
    bal_window: list["BalanceSheet"],
    attr: str,
    mcap_eur: float,
) -> tuple[float, float, float]:
    """(slope / total_assets_0, intercept / mcap, invalid_flag).

    `inc_window` and `bal_window` must be oldest-first.
    Flag=1 when fewer than 2 valid annual data points are available; in that
    case slope/intercept are 0.0 (mirrors training behaviour).
    """
    pairs: list[tuple[float, float]] = []
    for s in inc_window:
        y = _period_year(s.period)
        v = getattr(s, attr, None)
        if y is not None and v is not None:
            pairs.append((float(y), float(v)))
    if len(pairs) < 2:
        return 0.0, 0.0, 1.0

    base_year = pairs[0][0]
    m, c = _ols_m_c([p[0] - base_year for p in pairs], [p[1] for p in pairs])

    ta0 = next((float(b.total_assets) for b in bal_window if b.total_assets), None)
    slope_norm = max(-50.0, min(50.0, m / ta0)) if ta0 else 0.0
    icept_norm = max(-50.0, min(50.0, c / mcap_eur)) if mcap_eur > 0 else 0.0
    return slope_norm, icept_norm, 0.0


# ── public API ───────────────────────────────────────────────────────────────

def build_feature_vector(
    yahoo: "YahooProfile",
    snap: "MacroSnapshot",
) -> list[float] | None:
    """Build the 76-element feature vector. Returns None when the price-history
    scrape failed (no return / volatility features available)."""
    if yahoo.ret_252d_pct is None and yahoo.ret_126d_pct is None:
        return None

    def _v(x: float | None) -> float:
        return float(x) if x is not None else 0.0

    # ── market cap → EUR → log10(mcap+1) ─────────────────────────────────────
    mcap_eur = _mcap_to_eur(yahoo.market_cap, yahoo.currency, snap)
    log_mcap = math.log10(mcap_eur + 1.0) if mcap_eur and mcap_eur > 0 else 0.0

    # ── P/E with clip + availability flag ────────────────────────────────────
    pe_raw = yahoo.pe_ratio
    if pe_raw is not None:
        pe_feat = max(PE_RATIO_CLIP_LO, min(PE_RATIO_CLIP_HI, float(pe_raw)))
        pe_available = 1.0
    else:
        pe_feat = 0.0
        pe_available = 0.0

    # ── macro composite (VIX & DGS10), clamped to [0, 3] ─────────────────────
    vix_n = (snap.vix or 0.0) / 40.0
    d10_n = (snap.dgs10 or 0.0) / 5.0
    macro_composite = min(3.0, max(0.0, 0.5 * vix_n + 0.5 * d10_n))

    # ── annual statements: yahoo gives newest-first; reverse to oldest-first ─
    inc_oldest_first: list = list(reversed(yahoo.income_annual))
    bal_oldest_first: list = list(reversed(yahoo.balance_annual))
    inc_4 = inc_oldest_first[-4:] if len(inc_oldest_first) > 4 else inc_oldest_first
    bal_4 = bal_oldest_first[-4:] if len(bal_oldest_first) > 4 else bal_oldest_first

    p4_s, p4_c, p4_f = _trend_pair(inc_4,           bal_4,           "net_income",    mcap_eur or 1.0)
    pa_s, pa_c, pa_f = _trend_pair(inc_oldest_first, bal_oldest_first, "net_income",    mcap_eur or 1.0)
    r4_s, r4_c, r4_f = _trend_pair(inc_4,           bal_4,           "total_revenue", mcap_eur or 1.0)
    ra_s, ra_c, ra_f = _trend_pair(inc_oldest_first, bal_oldest_first, "total_revenue", mcap_eur or 1.0)

    # ── point-in-time fundamental ratios, using the latest annual statements ─
    latest_inc = inc_oldest_first[-1] if inc_oldest_first else None
    latest_bal = bal_oldest_first[-1] if bal_oldest_first else None
    rev = latest_inc.total_revenue if latest_inc and latest_inc.total_revenue else None
    ta  = latest_bal.total_assets  if latest_bal and latest_bal.total_assets  else None

    gross_margin = (
        max(-5.0, min(5.0, float(latest_inc.gross_profit) / float(rev)))
        if latest_inc and latest_inc.gross_profit is not None and rev else 0.0
    )
    operating_margin = (
        max(-5.0, min(5.0, float(latest_inc.operating_income) / float(rev)))
        if latest_inc and latest_inc.operating_income is not None and rev else 0.0
    )
    price_to_sales = (
        max(0.0, min(200.0, (mcap_eur or 0.0) / float(rev)))
        if rev and rev > 0 and mcap_eur and mcap_eur > 0 else 0.0
    )
    asset_turnover = (
        max(0.0, min(20.0, float(rev) / float(ta)))
        if rev and ta and ta > 0 else 0.0
    )

    # ── earnings_recency: years since latest annual period_end, floor 0 ──────
    # snapshot_date.year - period_end.year - 1, capped at 0 (no negative).
    # The pipeline runs "today" so we use today's year.
    import datetime as _dt
    today_year = _dt.date.today().year
    if latest_inc:
        latest_year = _period_year(latest_inc.period)
        earnings_recency = float(max(0, today_year - (latest_year or today_year) - 1)) if latest_year else 10.0
    else:
        earnings_recency = 10.0

    # ── assemble vector — ORDER MUST MATCH EXPECTED_FEATURE_NAMES ────────────
    vec: list[float] = [
        log_mcap,
        pe_feat,
        _v(yahoo.ret_1d_pct), _v(yahoo.ret_5d_pct), _v(yahoo.ret_21d_pct),
        _v(yahoo.ret_42d_pct), _v(yahoo.ret_126d_pct), _v(yahoo.ret_252d_pct),
        _v(yahoo.vol_21d_pct),
        macro_composite,
        _v(snap.sp500_ret_5d), _v(snap.sp500_ret_21d), _v(snap.sp500_ret_126d), _v(snap.sp500_ret_378d),
        _v(snap.wti_ret_5d), _v(snap.wti_ret_21d), _v(snap.wti_ret_126d), _v(snap.wti_ret_378d),
        _v(snap.hy_spread), _v(snap.t10y2y),
        _v(snap.etf_gld_ret_5d), _v(snap.etf_gld_ret_21d), _v(snap.etf_gld_ret_126d), _v(snap.etf_gld_ret_378d),
        _v(snap.etf_dbc_ret_5d), _v(snap.etf_dbc_ret_21d), _v(snap.etf_dbc_ret_126d), _v(snap.etf_dbc_ret_378d),
        _v(snap.etf_dba_ret_5d), _v(snap.etf_dba_ret_21d), _v(snap.etf_dba_ret_126d), _v(snap.etf_dba_ret_378d),
        _v(snap.etf_cper_ret_5d), _v(snap.etf_cper_ret_21d), _v(snap.etf_cper_ret_126d), _v(snap.etf_cper_ret_378d),
        _v(snap.etf_lit_ret_5d), _v(snap.etf_lit_ret_21d), _v(snap.etf_lit_ret_126d), _v(snap.etf_lit_ret_378d),
        _v(snap.etf_weat_ret_5d), _v(snap.etf_weat_ret_21d), _v(snap.etf_weat_ret_126d), _v(snap.etf_weat_ret_378d),
        0.0, 0.0, 0.0,                                       # sector-relative — no DB
        pe_available,
        p4_s, p4_c, p4_f,
        pa_s, pa_c, pa_f,
        r4_s, r4_c, r4_f,
        ra_s, ra_c, ra_f,
        gross_margin, operating_margin, price_to_sales, asset_turnover,
        earnings_recency,
        _v(yahoo.years_listed),
        _v(yahoo.price_norm_d0), _v(yahoo.price_norm_d1), _v(yahoo.price_norm_d2),
        _v(yahoo.price_norm_d3), _v(yahoo.price_norm_d4), _v(yahoo.price_norm_d5),
        _v(yahoo.price_norm_d6), _v(yahoo.price_norm_d7), _v(yahoo.price_norm_d8),
        _v(yahoo.price_norm_d9),
    ]
    assert len(vec) == len(EXPECTED_FEATURE_NAMES), (
        f"feature vector length {len(vec)} != expected {len(EXPECTED_FEATURE_NAMES)}"
    )
    return vec
