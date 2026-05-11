from __future__ import annotations

from src.pipelines.build_report.models import AssetVariation, VariationPeriods
from src.scrapers.technical.market_overview import ETFPerformance, MarketOverviewResult

_TARGET: list[tuple[str, str]] = [
    ("SPY",  "S&P 500"),
    ("EWQ",  "France"),
    ("EWZ",  "Brazil"),
    ("EWG",  "Germany"),
    ("EWJ",  "Japan"),
    ("MCHI", "China"),
    ("BND",  "Aggregate Bonds"),
    ("DBB",  "Industrial Metals"),
    ("DBA",  "Agricultural"),
    ("DBO",  "Oil"),
    ("FXE",  "EUR/USD"),
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
