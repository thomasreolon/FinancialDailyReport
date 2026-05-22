from __future__ import annotations

from src.pipelines.build_report.models import AssetVariation, VariationPeriods
from src.scrapers.technical.market_overview import ETFPerformance, MarketOverviewResult

# Ordered thematically: global equities → countries → bonds → commodities → FX.
# Row order in the report follows this list as-is (no perf-based sort).
_TARGET: list[tuple[str, str]] = [
    ("SPY",     "S&P 500"),
    ("VWCE.DE", "VWCE All-World"),
    ("EWQ",     "France"),
    ("EWG",     "Germany"),
    ("EWJ",     "Japan"),
    ("MCHI",    "China"),
    ("EWZ",     "Brazil"),
    ("BND",     "Aggregate Bonds"),
    ("GLD",     "Gold"),
    ("DBB",     "Industrial Metals"),
    ("DBO",     "Oil"),
    ("DBA",     "Agricultural"),
    ("FXE",     "EUR/USD"),
]


def build_variations(overview: MarketOverviewResult) -> list[AssetVariation]:
    perf_map: dict[str, ETFPerformance] = {
        etf.symbol: etf
        for group in overview.groups
        for etf in group.etfs
    }

    result = []
    for symbol, name in _TARGET:
        etf = perf_map.get(symbol)
        if etf:
            periods = VariationPeriods(
                one_day=etf.today_pct,
                five_days=etf.five_day_pct,
                one_month=etf.one_month_pct,
                one_year=etf.one_year_pct,
                three_years=etf.three_year_pct,
            )
        else:
            periods = VariationPeriods(
                one_day=None, five_days=None, one_month=None,
                one_year=None, three_years=None,
            )
        result.append(AssetVariation(symbol=symbol, name=name, periods=periods))
    return result
