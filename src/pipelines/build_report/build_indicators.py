from __future__ import annotations

from typing import Callable, Literal, NamedTuple

from src.pipelines.macro_indicators import MacroIndicatorsResult
from src.pipelines.build_report.models import IndicatorReport

Color = Literal["green", "grey", "red"]


class _Cfg(NamedTuple):
    name: str
    value_fn: Callable[[MacroIndicatorsResult], str]
    color_fn: Callable[[MacroIndicatorsResult], Color]
    help: str


def _clamp(val: float | None, low: float, high: float, invert: bool = False) -> Color:
    if val is None:
        return "grey"
    if not invert:
        return "green" if val <= low else "red" if val >= high else "grey"
    return "green" if val >= high else "red" if val <= low else "grey"


_CONFIGS: list[_Cfg] = [
    _Cfg(
        name="VIX (Volatility Index)",
        value_fn=lambda r: f"{r.vix:.1f}" if r.vix is not None else "N/A",
        color_fn=lambda r: _clamp(r.vix, 15.0, 25.0),
        help=(
            "The CBOE VIX measures implied 30-day volatility of S&P 500 options — the market's 'fear gauge'. "
            "Below 15 = calm, low-fear environment (green). 15–25 = normal uncertainty. "
            "Above 25 = elevated fear; spikes above 40 historically coincide with major sell-offs. "
            "VIX typically moves inversely to equity prices."
        ),
    ),
    _Cfg(
        name="Fear & Greed Index",
        value_fn=lambda r: f"{r.fear_greed:.0f} – {r.fear_greed_rating}" if r.fear_greed is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.fear_greed is not None and r.fear_greed > 60 else
            "red"   if r.fear_greed is not None and r.fear_greed < 40 else
            "grey"
        ),
        help=(
            "CNN's composite sentiment indicator (0–100) derived from 7 signals: price momentum, put/call ratio, "
            "VIX, safe-haven demand, junk-bond spreads, market breadth, and stock-price strength. "
            "Above 60 = greed (bullish). Below 40 = fear (bearish). Extreme readings are contrarian: "
            "extreme greed can precede corrections; extreme fear often marks bottoms."
        ),
    ),
    _Cfg(
        name="Yield Curve (10Y–3M)",
        value_fn=lambda r: f"{r.yield_curve_10y3m:+.2f}%" if r.yield_curve_10y3m is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.yield_curve_10y3m is not None and r.yield_curve_10y3m > 0.5 else
            "red"   if r.yield_curve_10y3m is not None and r.yield_curve_10y3m < -0.5 else
            "grey"
        ),
        help=(
            "Spread between 10-year and 3-month US Treasury yields. Positive = normal curve (green). "
            "Negative (inverted) has preceded every US recession since the 1960s, typically 6–18 months later. "
            "Above +0.5% = healthy. Below -0.5% = inversion = recession warning (red)."
        ),
    ),
    _Cfg(
        name="Fed Funds Rate",
        value_fn=lambda r: f"{r.fed_funds_rate:.2f}%" if r.fed_funds_rate is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.fed_funds_rate is not None and r.fed_funds_rate < 3.0 else
            "red"   if r.fed_funds_rate is not None and r.fed_funds_rate > 5.0 else
            "grey"
        ),
        help=(
            "The overnight interbank lending rate set by the Federal Reserve — the base cost of money. "
            "Low rates (<3%) = accommodative policy, cheap credit, supports equity valuations. "
            "High rates (>5%) = restrictive, compresses growth-stock multiples and increases debt costs. "
            "Rate direction matters as much as level: a cutting cycle is bullish, a hiking cycle is bearish."
        ),
    ),
    _Cfg(
        name="Fed Rate Decision Probability",
        value_fn=lambda r: r.fed_june_probability or "N/A",
        color_fn=lambda r: "grey",
        help=(
            "CME FedWatch probability for the next FOMC meeting — derived from federal funds futures prices. "
            "Shows market-implied odds of a rate hold, cut, or hike. "
            "High probability of a cut is bullish for equities and bonds; "
            "high probability of a hike is bearish, especially for growth stocks and long-duration bonds."
        ),
    ),
    _Cfg(
        name="Fed Balance Sheet",
        value_fn=lambda r: f"${r.fed_balance_sheet_trn:.2f}T" if r.fed_balance_sheet_trn is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.fed_balance_sheet_trn is not None and r.fed_balance_sheet_trn > 8.0 else
            "red"   if r.fed_balance_sheet_trn is not None and r.fed_balance_sheet_trn < 7.0 else
            "grey"
        ),
        help=(
            "The Fed's total assets — mainly Treasuries and mortgage-backed securities. "
            "Expanding balance sheet (QE) injects liquidity, supporting asset prices. "
            "Shrinking (QT) withdraws liquidity, pressuring valuations. "
            "Size >$8T reflects historically high accommodation; rapid shrinkage is a tightening headwind."
        ),
    ),
    _Cfg(
        name="US M2 Money Supply (YoY%)",
        value_fn=lambda r: (
            f"${r.m2_us_trn:.1f}T ({r.m2_us_yoy_pct:+.1f}% YoY)"
            if r.m2_us_trn is not None and r.m2_us_yoy_pct is not None else "N/A"
        ),
        color_fn=lambda r: (
            "green" if r.m2_us_yoy_pct is not None and 2.0 <= r.m2_us_yoy_pct <= 8.0 else
            "red"   if r.m2_us_yoy_pct is not None and r.m2_us_yoy_pct < 0 else
            "grey"
        ),
        help=(
            "US M2 includes cash, deposits, savings, and money market accounts — the broadest common money measure. "
            "Rapid growth (>8% YoY) fuels inflation and asset bubbles. Negative growth (monetary contraction) is "
            "historically rare and precedes economic stress. Moderate growth (2–8%) supports normal activity."
        ),
    ),
    _Cfg(
        name="Global M2 Money Supply",
        value_fn=lambda r: f"${r.global_m2_trn:.0f}T" if r.global_m2_trn is not None else "N/A",
        color_fn=lambda r: "grey",
        help=(
            "Aggregate money supply of all major economies in USD equivalent. "
            "When global central banks expand M2 in sync, financial conditions loosen, supporting equities and risk assets. "
            "When they contract together (as in 2022), risk assets typically fall in tandem. "
            "Changes in global M2 tend to lead equity markets by roughly 3–6 months."
        ),
    ),
    _Cfg(
        name="Fed Overnight RRP Facility",
        value_fn=lambda r: f"${r.rrp_facility_bln:.0f}B" if r.rrp_facility_bln is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.rrp_facility_bln is not None and r.rrp_facility_bln < 100 else
            "red"   if r.rrp_facility_bln is not None and r.rrp_facility_bln > 500 else
            "grey"
        ),
        help=(
            "Cash parked by money market funds at the Fed overnight. When high (>$500B), idle liquidity is "
            "trapped at the Fed rather than flowing into markets. Declining RRP is bullish: that cash is "
            "moving into T-bills and other assets. Near zero means excess post-pandemic liquidity is fully absorbed."
        ),
    ),
    _Cfg(
        name="FINRA Margin Debt",
        value_fn=lambda r: f"${r.finra_margin_debt_bln:.0f}B" if r.finra_margin_debt_bln is not None else "N/A",
        color_fn=lambda r: "grey",
        help=(
            "Total borrowed capital used by investors to buy securities on margin. "
            "High and rising margin debt indicates leverage and investor confidence — but also fragility. "
            "Sharp declines trigger forced liquidations (margin calls), amplifying market sell-offs. "
            "Rapid increases near all-time highs are a classic late-cycle warning signal."
        ),
    ),
    _Cfg(
        name="SPY/M2 Valuation Ratio",
        value_fn=lambda r: (
            f"{r.spy_m2_ratio:.1f} ({r.spy_m2_ratio_label})"
            if r.spy_m2_ratio is not None and r.spy_m2_ratio_label else "N/A"
        ),
        color_fn=lambda r: (
            "green" if r.spy_m2_ratio_label == "compressed" else
            "red"   if r.spy_m2_ratio_label == "elevated"   else
            "grey"
        ),
        help=(
            "S&P 500 level divided by US M2 in trillions — a liquidity-adjusted valuation gauge. "
            "Compressed (<150): stocks are cheap relative to money supply. "
            "Elevated (>250): stocks are expensive relative to liquidity, raising correction risk. "
            "Distinguishes market moves driven by real growth from those driven purely by monetary expansion."
        ),
    ),
    _Cfg(
        name="5Y Breakeven Inflation",
        value_fn=lambda r: f"{r.breakeven_5y:.2f}%" if r.breakeven_5y is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.breakeven_5y is not None and 1.5 <= r.breakeven_5y <= 2.5 else
            "red"   if r.breakeven_5y is not None and r.breakeven_5y > 3.0 else
            "grey"
        ),
        help=(
            "Market-implied average annual inflation expectation over 5 years, from TIPS vs nominal yield spread. "
            "Anchored near 2% (green) = Fed credibility intact, rate path predictable. "
            "Above 3% = bond markets doubt the Fed, raising the risk of more hikes or 'higher for longer' rates. "
            "Short-term signal; more volatile than the 10-year breakeven."
        ),
    ),
    _Cfg(
        name="10Y Breakeven Inflation",
        value_fn=lambda r: f"{r.breakeven_10y:.2f}%" if r.breakeven_10y is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.breakeven_10y is not None and 1.5 <= r.breakeven_10y <= 2.5 else
            "red"   if r.breakeven_10y is not None and r.breakeven_10y > 3.0 else
            "grey"
        ),
        help=(
            "The 10-year inflation expectation from TIPS spreads — the most-watched long-term inflation signal. "
            "Near 2% target (green) = market believes inflation normalizes over the decade. "
            "Rising above 2.5% pressures the Fed to keep rates higher for longer, which is bearish "
            "for growth stocks and long-duration bonds. A primary driver of the equity risk premium."
        ),
    ),
    _Cfg(
        name="Core PCE Inflation (YoY)",
        value_fn=lambda r: f"{r.core_pce_yoy:.2f}%" if r.core_pce_yoy is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.core_pce_yoy is not None and r.core_pce_yoy <= 2.5 else
            "red"   if r.core_pce_yoy is not None and r.core_pce_yoy > 3.5 else
            "grey"
        ),
        help=(
            "The Federal Reserve's preferred inflation gauge (Personal Consumption Expenditures, ex-food & energy). "
            "The Fed's 2% target is defined on this measure. Below 2.5% = on track (green). "
            "Above 3.5% = well above target, keeps the Fed hawkish (red). "
            "Declining PCE is the key condition for rate cuts — the single most market-moving monthly print."
        ),
    ),
    _Cfg(
        name="ISM Manufacturing PMI",
        value_fn=lambda r: f"{r.ism_manufacturing_pmi:.1f}" if r.ism_manufacturing_pmi is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.ism_manufacturing_pmi is not None and r.ism_manufacturing_pmi > 50 else
            "red"   if r.ism_manufacturing_pmi is not None and r.ism_manufacturing_pmi < 48 else
            "grey"
        ),
        help=(
            "Monthly survey of manufacturing purchasing managers. Above 50 = expansion (factories growing). "
            "Below 50 = contraction. Leading indicator for economic activity by 1–2 quarters. "
            "Sustained readings below 48 historically coincide with recessions. "
            "New orders and employment sub-indices are watched most closely for forward momentum."
        ),
    ),
    _Cfg(
        name="Shiller CAPE Ratio",
        value_fn=lambda r: f"{r.shiller_cape:.1f}" if r.shiller_cape is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.shiller_cape is not None and r.shiller_cape < 25 else
            "red"   if r.shiller_cape is not None and r.shiller_cape > 35 else
            "grey"
        ),
        help=(
            "S&P 500 price divided by the 10-year average inflation-adjusted earnings. Historical average ~17; "
            "internet-bubble peak ~44. Above 35 = historically expensive, associated with below-average "
            "10-year forward returns. Below 25 = historically reasonable. "
            "Better for long-run return forecasting than short-term market timing."
        ),
    ),
    _Cfg(
        name="Buffett Indicator",
        value_fn=lambda r: f"{r.buffett_indicator_pct:.0f}%" if r.buffett_indicator_pct is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.buffett_indicator_pct is not None and r.buffett_indicator_pct < 100 else
            "red"   if r.buffett_indicator_pct is not None and r.buffett_indicator_pct > 150 else
            "grey"
        ),
        help=(
            "Total US stock market cap divided by GDP — Warren Buffett's preferred macro valuation gauge. "
            "Below 80% = undervalued. 80–115% = fair value. Above 150% = overvalued ('playing with fire'). "
            "The globalization of US companies and low rates since 2008 have structurally elevated this ratio; "
            "it's best used as a relative historical comparison rather than an absolute signal."
        ),
    ),
    _Cfg(
        name="Equity Risk Premium",
        value_fn=lambda r: f"{r.equity_risk_premium:+.2f}%" if r.equity_risk_premium is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.equity_risk_premium is not None and r.equity_risk_premium > 3.0 else
            "red"   if r.equity_risk_premium is not None and r.equity_risk_premium < 1.0 else
            "grey"
        ),
        help=(
            "Forward earnings yield (1/forward P/E) minus 10-year real yield — the extra return stocks offer vs bonds. "
            "Above 3% = stocks are attractively priced vs risk-free bonds (green). "
            "Below 1% = equities offer minimal premium over bonds, making allocation to equities less compelling (red). "
            "A negative ERP means bonds yield more than stocks on a risk-adjusted basis."
        ),
    ),
    _Cfg(
        name="OECD Leading Indicator (US)",
        value_fn=lambda r: (
            f"{r.lei_conference_board:.2f} ({r.lei_mom_pct:+.2f}% MoM)"
            if r.lei_conference_board is not None and r.lei_mom_pct is not None else "N/A"
        ),
        color_fn=lambda r: (
            "green" if r.lei_conference_board is not None and r.lei_conference_board > 100.0 and (r.lei_mom_pct or 0) > 0 else
            "red"   if r.lei_conference_board is not None and r.lei_conference_board < 99.0  and (r.lei_mom_pct or 0) < 0 else
            "grey"
        ),
        help=(
            "OECD Composite Leading Indicator for the US — a 100-normalized index of forward-looking signals "
            "(permits, orders, confidence, credit). Above 100 and rising = expansion trend. "
            "Below 100 and falling = potential slowdown ahead, leads GDP by 6–9 months. "
            "Consecutive monthly declines below 99 are a strong early recession warning."
        ),
    ),
    _Cfg(
        name="Copper/Gold Ratio",
        value_fn=lambda r: f"{r.copper_gold_ratio:.5f}" if r.copper_gold_ratio is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.copper_gold_ratio is not None and r.copper_gold_ratio > 0.00040 else
            "red"   if r.copper_gold_ratio is not None and r.copper_gold_ratio < 0.00020 else
            "grey"
        ),
        help=(
            "Copper (industrial demand proxy) divided by gold (safe-haven proxy). "
            "Rising ratio = growth optimism, industry buying copper for manufacturing and construction (green). "
            "Falling ratio = risk-off, flight to safety (red). "
            "The ratio also leads 10-year Treasury yields (Gundlach signal) — useful for anticipating rate direction."
        ),
    ),
    _Cfg(
        name="S&P 500 Forward P/E",
        value_fn=lambda r: f"{r.sp500_fwd_pe:.1f}x" if r.sp500_fwd_pe is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.sp500_fwd_pe is not None and r.sp500_fwd_pe < 18 else
            "red"   if r.sp500_fwd_pe is not None and r.sp500_fwd_pe > 22 else
            "grey"
        ),
        help=(
            "S&P 500 price divided by consensus 12-month forward EPS estimates. Historical average ~16x. "
            "Below 18x = reasonably priced vs modern norms. Above 22x = high expectations, "
            "vulnerable to earnings misses or rising rates (which reduce the present value of future earnings). "
            "The single most widely watched equity valuation multiple."
        ),
    ),
    _Cfg(
        name="S&P 500 EPS Growth (YoY)",
        value_fn=lambda r: (
            f"{r.sp500_eps_growth_q:+.1f}% ({r.sp500_eps_growth_quarter})"
            if r.sp500_eps_growth_q is not None and r.sp500_eps_growth_quarter else "N/A"
        ),
        color_fn=lambda r: (
            "green" if r.sp500_eps_growth_q is not None and r.sp500_eps_growth_q > 10 else
            "red"   if r.sp500_eps_growth_q is not None and r.sp500_eps_growth_q < 0  else
            "grey"
        ),
        help=(
            "Year-over-year blended EPS growth for the S&P 500 in the most recent quarter "
            "(combines actual reports + remaining estimates). Above 10% = strong earnings cycle, "
            "supports current valuations (green). Negative = earnings contraction, often triggers "
            "multiple compression and market weakness (red). 0–10% = moderate, sustainable growth."
        ),
    ),
    _Cfg(
        name="EuroStoxx 50 EPS Growth",
        value_fn=lambda r: f"{r.eurostoxx50_fwd_eps_growth:+.1f}%" if r.eurostoxx50_fwd_eps_growth is not None else "N/A",
        color_fn=lambda r: (
            "green" if r.eurostoxx50_fwd_eps_growth is not None and r.eurostoxx50_fwd_eps_growth > 8 else
            "red"   if r.eurostoxx50_fwd_eps_growth is not None and r.eurostoxx50_fwd_eps_growth < 0 else
            "grey"
        ),
        help=(
            "Forward EPS growth estimate for the EuroStoxx 50 (50 largest European companies). "
            "European equities trade at a discount to US (lower P/E), so earnings growth is the primary alpha driver. "
            "Strong growth (>8%) supports European equity allocation. "
            "Negative estimates reflect macro headwinds: energy prices, geopolitical risk, or EUR strength."
        ),
    ),
    _Cfg(
        name="Leading Sectors (EPS Growth)",
        value_fn=lambda r: r.leading_sectors or "N/A",
        color_fn=lambda r: "grey",
        help=(
            "S&P 500 sectors with the highest YoY EPS growth in the current reporting quarter. "
            "Leading sectors attract capital inflows and tend to outperform near-term. "
            "Defensive sectors leading (Healthcare, Utilities, Staples) = late-cycle signal. "
            "Technology and Financials leading together = risk-on, early-to-mid cycle growth regime."
        ),
    ),
]


def build_indicators(result: MacroIndicatorsResult) -> list[IndicatorReport]:
    reports = []
    for cfg in _CONFIGS:
        try:
            value = cfg.value_fn(result)
            color = cfg.color_fn(result)
        except Exception:
            value = "N/A"
            color = "grey"
        reports.append(IndicatorReport(name=cfg.name, value=value, color=color, help=cfg.help))
    return reports
