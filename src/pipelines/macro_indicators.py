"""Macro indicators pipeline.

Runs all indicator scrapers, aggregates results into a single model, and uses
Gemini with Google Search to fill any gaps that scrapers could not fetch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from src.api.gemini import search_then_extract


# ── result model ─────────────────────────────────────────────────────────────

class MacroIndicatorsResult(BaseModel):
    # Market Sentiment & Volatility
    vix: float | None = None
    vix_date: str | None = None
    fear_greed: float | None = None
    fear_greed_rating: str | None = None

    # Fed & Rates
    yield_curve_10y3m: float | None = None
    fed_funds_rate: float | None = None
    fed_june_probability: str | None = None   # e.g. "hold 82%, cut 25bp 18%"

    # Liquidity & Leverage
    fed_balance_sheet_trn: float | None = None
    m2_us_trn: float | None = None
    m2_us_yoy_pct: float | None = None
    global_m2_trn: float | None = None
    rrp_facility_bln: float | None = None
    finra_margin_debt_bln: float | None = None
    spy_m2_ratio: float | None = None
    spy_m2_ratio_label: str | None = None

    # Inflation & Real Economy
    breakeven_5y: float | None = None
    breakeven_10y: float | None = None
    core_pce_yoy: float | None = None
    ism_manufacturing_pmi: float | None = None

    # Valuations
    shiller_cape: float | None = None
    buffett_indicator_pct: float | None = None
    equity_risk_premium: float | None = None

    # Recession Early Warning
    lei_conference_board: float | None = None
    lei_mom_pct: float | None = None
    copper_gold_ratio: float | None = None

    # Earnings
    sp500_fwd_eps: float | None = None
    sp500_fwd_pe: float | None = None
    sp500_eps_growth_q: float | None = None
    sp500_eps_growth_quarter: str | None = None
    eurostoxx50_fwd_eps_growth: float | None = None
    leading_sectors: str | None = None

    # Metadata
    fetched_at: str = ""
    gemini_filled: list[str] = Field(default_factory=list)
    data_dates: dict[str, str] = Field(default_factory=dict)  # field → data date


# ── scraper runners ───────────────────────────────────────────────────────────

def _safe_run(name: str, fn) -> Any:
    try:
        result = fn()
        return result
    except Exception as exc:
        print(f"    [warn] {name} failed: {exc}")
        return None


def _collect_scraped() -> MacroIndicatorsResult:
    from src.scrapers.indicator.vix import scrape_vix
    from src.scrapers.indicator.fear_greed import scrape_fear_greed
    from src.scrapers.indicator.yield_curve import scrape_yield_curve
    from src.scrapers.indicator.fed_funds_rate import scrape_fed_funds_rate
    from src.scrapers.indicator.fed_june_probability import scrape_fed_june_probability
    from src.scrapers.indicator.fed_balance_sheet import scrape_fed_balance_sheet
    from src.scrapers.indicator.m2_us import scrape_m2_us
    from src.scrapers.indicator.global_m2 import scrape_global_m2
    from src.scrapers.indicator.rrp_facility import scrape_rrp_facility
    from src.scrapers.indicator.margin_debt import scrape_margin_debt
    from src.scrapers.indicator.spy_m2_ratio import scrape_spy_m2_ratio
    from src.scrapers.indicator.breakeven_5y import scrape_breakeven_5y
    from src.scrapers.indicator.breakeven_10y import scrape_breakeven_10y
    from src.scrapers.indicator.core_pce import scrape_core_pce
    from src.scrapers.indicator.ism_pmi import scrape_ism_pmi
    from src.scrapers.indicator.shiller_cape import scrape_shiller_cape
    from src.scrapers.indicator.buffett_indicator import scrape_buffett_indicator
    from src.scrapers.indicator.equity_risk_premium import scrape_equity_risk_premium
    from src.scrapers.indicator.lei import scrape_lei
    from src.scrapers.indicator.copper_gold_ratio import scrape_copper_gold_ratio
    from src.scrapers.indicator.sp500_fwd_eps import scrape_sp500_fwd_eps
    from src.scrapers.indicator.sp500_fwd_pe import scrape_sp500_fwd_pe
    from src.scrapers.indicator.sp500_eps_growth import scrape_sp500_eps_growth
    from src.scrapers.indicator.eurostoxx50_fwd_eps import scrape_eurostoxx50_fwd_eps
    from src.scrapers.indicator.leading_sectors import scrape_leading_sectors

    r = MacroIndicatorsResult()

    vix = _safe_run("vix", scrape_vix)
    if vix:
        r.vix = vix.value
        r.vix_date = vix.date
        r.data_dates["vix"] = vix.date

    fg = _safe_run("fear_greed", scrape_fear_greed)
    if fg:
        r.fear_greed = fg.score
        r.fear_greed_rating = fg.rating
        r.data_dates["fear_greed"] = fg.date

    yc = _safe_run("yield_curve", scrape_yield_curve)
    if yc:
        r.yield_curve_10y3m = yc.spread_pct
        r.data_dates["yield_curve_10y3m"] = yc.date

    ff = _safe_run("fed_funds_rate", scrape_fed_funds_rate)
    if ff:
        r.fed_funds_rate = ff.rate_pct
        r.data_dates["fed_funds_rate"] = ff.date

    _safe_run("fed_june_probability", scrape_fed_june_probability)  # always None, Gemini fills

    fbs = _safe_run("fed_balance_sheet", scrape_fed_balance_sheet)
    if fbs:
        r.fed_balance_sheet_trn = fbs.value_trn
        r.data_dates["fed_balance_sheet"] = fbs.date

    m2 = _safe_run("m2_us", scrape_m2_us)
    if m2:
        r.m2_us_trn = m2.value_trn
        r.m2_us_yoy_pct = m2.yoy_pct
        r.data_dates["m2_us"] = m2.date

    gm2 = _safe_run("global_m2", scrape_global_m2)
    if gm2:
        r.global_m2_trn = gm2.value_trn

    rrp = _safe_run("rrp_facility", scrape_rrp_facility)
    if rrp:
        r.rrp_facility_bln = rrp.value_bln
        r.data_dates["rrp_facility"] = rrp.date

    md = _safe_run("margin_debt", scrape_margin_debt)
    if md:
        r.finra_margin_debt_bln = md.value_bln
        r.data_dates["finra_margin_debt"] = md.date

    sm2 = _safe_run("spy_m2_ratio", scrape_spy_m2_ratio)
    if sm2:
        r.spy_m2_ratio = sm2.ratio
        r.spy_m2_ratio_label = sm2.label

    b5 = _safe_run("breakeven_5y", scrape_breakeven_5y)
    if b5:
        r.breakeven_5y = b5.rate_pct
        r.data_dates["breakeven_5y"] = b5.date

    b10 = _safe_run("breakeven_10y", scrape_breakeven_10y)
    if b10:
        r.breakeven_10y = b10.rate_pct
        r.data_dates["breakeven_10y"] = b10.date

    pce = _safe_run("core_pce", scrape_core_pce)
    if pce:
        r.core_pce_yoy = pce.yoy_pct
        r.data_dates["core_pce"] = pce.date

    ism = _safe_run("ism_pmi", scrape_ism_pmi)
    if ism:
        r.ism_manufacturing_pmi = ism.value
        r.data_dates["ism_pmi"] = ism.date

    cape = _safe_run("shiller_cape", scrape_shiller_cape)
    if cape:
        r.shiller_cape = cape.value
        r.data_dates["shiller_cape"] = cape.date

    buf = _safe_run("buffett_indicator", scrape_buffett_indicator)
    if buf:
        r.buffett_indicator_pct = buf.ratio_pct
        r.data_dates["buffett_indicator"] = buf.date

    erp = _safe_run("equity_risk_premium", scrape_equity_risk_premium)
    if erp:
        r.equity_risk_premium = erp.erp_pct
        # Store real yield for post-Gemini ERP calculation if forward PE was unavailable
        if erp.real_yield_10y is not None:
            r.data_dates["real_yield_10y"] = str(erp.real_yield_10y)
        r.data_dates["equity_risk_premium"] = erp.date

    lei = _safe_run("lei", scrape_lei)
    if lei:
        r.lei_conference_board = lei.value
        r.lei_mom_pct = lei.mom_pct
        r.data_dates["lei"] = lei.date

    cgr = _safe_run("copper_gold_ratio", scrape_copper_gold_ratio)
    if cgr:
        r.copper_gold_ratio = cgr.ratio
        r.data_dates["copper_gold_ratio"] = cgr.date

    feps = _safe_run("sp500_fwd_eps", scrape_sp500_fwd_eps)
    if feps:
        r.sp500_fwd_eps = feps.fwd_eps

    fpe = _safe_run("sp500_fwd_pe", scrape_sp500_fwd_pe)
    if fpe:
        r.sp500_fwd_pe = fpe.fwd_pe

    epsg = _safe_run("sp500_eps_growth", scrape_sp500_eps_growth)
    if epsg:
        r.sp500_eps_growth_q = epsg.growth_pct
        r.sp500_eps_growth_quarter = epsg.quarter

    eu = _safe_run("eurostoxx50_fwd_eps", scrape_eurostoxx50_fwd_eps)
    if eu:
        r.eurostoxx50_fwd_eps_growth = eu.growth_pct

    ls = _safe_run("leading_sectors", scrape_leading_sectors)
    if ls:
        r.leading_sectors = str(ls.sectors)

    return r


# ── Gemini fallback ───────────────────────────────────────────────────────────

# Typed schema for all fields that scrapers cannot reliably fetch.
# All fields are Optional so the model can return null for anything uncertain.
class _GeminiFill(BaseModel):
    fed_june_probability: str | None = Field(
        None,
        description=(
            "CME FedWatch probability for the next FOMC meeting. "
            "Format: 'hold X%, cut 25bp Y%' including the meeting date."
        ),
    )
    global_m2_trn: float | None = Field(
        None,
        description="Global M2 money supply USD-equivalent estimate in trillions.",
    )
    buffett_indicator_pct: float | None = Field(
        None,
        description="Buffett Indicator: total US stock market cap divided by GDP, as a percentage.",
    )
    sp500_fwd_eps: float | None = Field(
        None,
        description="S&P 500 consensus forward EPS estimate for the current fiscal year (FactSet).",
    )
    sp500_fwd_pe: float | None = Field(
        None,
        description="S&P 500 forward 12-month P/E ratio (FactSet EarningsInsight).",
    )
    sp500_eps_growth_q: float | None = Field(
        None,
        description="S&P 500 blended EPS growth YoY % for the most recently reported quarter.",
    )
    sp500_eps_growth_quarter: str | None = Field(
        None,
        description="Quarter label for sp500_eps_growth_q, e.g. 'Q1 2025'.",
    )
    eurostoxx50_fwd_eps_growth: float | None = Field(
        None,
        description="EuroStoxx 50 forward EPS growth % estimate for the current year.",
    )
    leading_sectors: str | None = Field(
        None,
        description=(
            "Top 2-3 S&P 500 sectors by EPS growth this quarter with approximate % figures. "
            "Format: 'Technology +18%, Healthcare +12%, Financials +9%'."
        ),
    )
    shiller_cape: float | None = Field(
        None,
        description="Current S&P 500 Shiller CAPE (cyclically adjusted P/E) ratio.",
    )
    ism_manufacturing_pmi: float | None = Field(
        None,
        description="Latest ISM Manufacturing PMI reading (above 50 = expansion, below 50 = contraction).",
    )


# Fields in _GeminiFill that map directly to MacroIndicatorsResult fields
_GEMINI_FILL_FIELDS = set(_GeminiFill.model_fields.keys())


def _identify_missing(r: MacroIndicatorsResult) -> list[str]:
    data = r.model_dump()
    return [f for f in _GEMINI_FILL_FIELDS if data.get(f) is None]


def _fill_with_gemini(r: MacroIndicatorsResult, missing: list[str]) -> None:
    if not missing:
        return

    missing_descriptions = "\n".join(
        f"- {f}: {_GeminiFill.model_fields[f].description}"
        for f in missing
        if f in _GeminiFill.model_fields
    )
    search_prompt = (
        f"You are a financial data assistant. Today is {datetime.now().date().isoformat()}. "
        f"Search the web and find the most current values for these economic/market indicators:\n"
        f"{missing_descriptions}\n\n"
        "Use the most authoritative and recent sources available "
        "(CME FedWatch, FactSet, ISM, gurufocus, macromicro.me, etc.). "
        "Report each value clearly with its source and approximate data date."
    )

    try:
        filled_data = search_then_extract(search_prompt, _GeminiFill)
        result_dict = r.model_dump()
        filled = []
        for field in missing:
            val = getattr(filled_data, field, None)
            if val is not None:
                result_dict[field] = val
                filled.append(field)
        updated = MacroIndicatorsResult(**result_dict)
        r.__dict__.update(updated.__dict__)
        r.gemini_filled.extend(filled)
    except Exception as exc:
        print(f"    [warn] Gemini fill failed: {exc}")


# ── public API ────────────────────────────────────────────────────────────────

def run_pipeline() -> MacroIndicatorsResult:
    print("  Collecting scraped indicators...")
    result = _collect_scraped()
    result.fetched_at = datetime.now(timezone.utc).isoformat()

    missing = _identify_missing(result)
    if missing:
        print(f"  {len(missing)} missing fields → Gemini with web search: {missing}")
        _fill_with_gemini(result, missing)
        print(f"  Gemini filled: {result.gemini_filled}")
    else:
        print("  All indicators collected from scrapers.")

    # Derive ERP from filled forward P/E and scraped real yield if still missing
    if result.equity_risk_premium is None and result.sp500_fwd_pe:
        real_yield_str = result.data_dates.get("real_yield_10y")
        if real_yield_str:
            try:
                real_yield = float(real_yield_str)
                fwd_earnings_yield = round(100 / result.sp500_fwd_pe, 3)
                result.equity_risk_premium = round(fwd_earnings_yield - real_yield, 3)
                result.gemini_filled.append("equity_risk_premium (derived)")
            except (ValueError, ZeroDivisionError):
                pass

    return result
