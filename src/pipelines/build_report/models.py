from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChartPoint(BaseModel):
    period: str
    net_revenue: float | None
    ebitda: float | None        # operating_income as proxy
    earnings: float | None      # net_income
    debt_assets_ratio: float | None


class CompanyReport(BaseModel):
    ticker: str
    name: str | None
    price: float | None
    price_now: float | None
    text: str
    market_cap: float | None
    pe: float | None
    pb: float | None
    description: str | None
    chart: list[ChartPoint] = Field(default_factory=list)


class IndicatorReport(BaseModel):
    name: str
    value: float | None        # normalized numeric value for ML/analysis
    unit: str = ""             # display hint: "pct", "pct+", "T$", "B$", "x", ""
    label: str | None = None   # secondary string (rating, quarter, label)
    color: Literal["green", "grey", "red"]
    help: str


class VariationPeriods(BaseModel):
    one_day: float | None
    five_days: float | None
    one_month: float | None
    one_year: float | None
    three_years: float | None


class AssetVariation(BaseModel):
    symbol: str
    name: str
    periods: VariationPeriods
    # CDS rows only: a rising spread means rising credit risk (bad), the
    # opposite of a rising price — period cells should color inverted.
    invert_color: bool = False
    # CDS rows only: static current value (basis points) shown in the "Now"
    # column. ETF rows leave this None and get a live Yahoo price via JS
    # instead (no live feed exists for CDS spreads).
    now_value: float | None = None
    now_suffix: str = ""


class PersonalView(BaseModel):
    title: str
    article: str


class TechDiscovery(BaseModel):
    title: str
    summary: str
    impact: str | None = None


class BenchmarkQuote(BaseModel):
    symbol: str
    name: str
    price: float | None


class DailyReport(BaseModel):
    title: str
    article: str
    companies: list[CompanyReport] = Field(default_factory=list)
    companies_sentiment: Literal["BEARISH", "NEUTRAL", "BULLISH"] | None = None
    indicators: list[IndicatorReport] = Field(default_factory=list)
    title2: str
    article2: str
    variations: list[AssetVariation] = Field(default_factory=list)
    generated_at: str
    personal_view: PersonalView | None = None
    market_compare: list[BenchmarkQuote] = Field(default_factory=list)
    tech_discoveries: list[TechDiscovery] = Field(default_factory=list)
