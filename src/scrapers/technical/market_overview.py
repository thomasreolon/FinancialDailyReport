"""
Yahoo Finance spark scraper — market overview across ~50 ETFs.

One batch call to /v7/finance/spark fetches 3 years of daily prices for all
symbols, from which six standard period returns are computed:
  Today, 5 Days, 1 Month, YTD, 1 Year, 3 Years

Groupings mirror the SeekAlpha market overview layout.
Note: IFLN from the SeekAlpha layout does not resolve as a major ETF;
replaced with HYG (iShares iBoxx $ High Yield Corporate Bond ETF).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_BASE = "https://query1.finance.yahoo.com"
_SPARK_URL = f"{_BASE}/v7/finance/spark"
_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
    "Accept": "application/json",
}

# ── ETF groups ────────────────────────────────────────────────────────────────

GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("US Equities", [
        ("SPY", "S&P 500"), ("DIA", "DJIA"), ("QQQ", "NASDAQ 100"),
        ("MDY", "Mid Cap"), ("IJR", "Small Cap"), ("IWC", "Micro Cap"),
    ]),
    ("US Equity Sectors", [
        ("XLK", "Technology"), ("XLV", "Healthcare"), ("XLP", "Consumer Staples"),
        ("XLU", "Utilities"), ("XLY", "Consumer Discr."), ("XLC", "Communication Svcs"),
        ("XLB", "Basic Materials"), ("XLF", "Financial Services"),
        ("XLI", "Industrials"), ("XLE", "Energy"), ("XLRE", "Real Estate"),
    ]),
    ("US Equity Factors", [
        ("IUSV", "Value"), ("IUSG", "Growth"), ("QUAL", "Quality"),
        ("USMV", "Low Volatility"), ("VYM", "High Dividend Yield"),
        ("MTUM", "Momentum"), ("DGRO", "Dividend Growth"), ("RSP", "Equal Weight"),
    ]),
    ("Global Equities", [
        ("ACWI", "World Equities"), ("VWCE.DE", "VWCE All-World"),
        ("IEMG", "Emerging Markets"),
        ("SPDW", "World ex-US"), ("VEA", "Developed Markets"), ("IEFA", "EAFE"),
    ]),
    ("Countries", [
        ("EWZ", "Brazil"), ("EWQ", "France"), ("EWU", "U.K."),
        ("EWG", "Germany"), ("VTI", "U.S."), ("EWJ", "Japan"), ("MCHI", "China"),
    ]),
    ("Bonds", [
        ("TLT", "20+ Year Treasury"), ("BND", "Aggregate Bonds"),
        ("TIP", "TIPS"), ("HYG", "High Yield Bonds"),
        ("BWX", "International Govt. Bonds"), ("VCSH", "Short Term Corporate"),
    ]),
    ("Commodities", [
        ("DBB", "Industrial Metals"), ("GLD", "Gold"), ("SLV", "Silver"),
        ("PPLT", "Platinum"), ("DBA", "Agricultural"), ("DBO", "Oil"),
        ("UNG", "Natural Gas"), ("CORN", "Corn"), ("SOYB", "Soybeans"),
        ("DBC", "Broad Commodities"), ("CPER", "Copper"),
        ("LIT", "Lithium & Battery"), ("WEAT", "Wheat"),
    ]),
    ("Currencies", [
        ("UUP", "US Dollar"), ("FXB", "British Pound"),
        ("FXE", "Euro"), ("FXY", "Japanese Yen"),
    ]),
]

_ALL_SYMBOLS: list[str] = [sym for _, etfs in GROUPS for sym, _ in etfs]
_NAME_MAP: dict[str, str] = {sym: name for _, etfs in GROUPS for sym, name in etfs}


# ── models ────────────────────────────────────────────────────────────────────

class ETFPerformance(BaseModel):
    symbol: str
    name: str
    today_pct: float | None
    five_day_pct: float | None
    one_month_pct: float | None
    ytd_pct: float | None
    one_year_pct: float | None
    three_year_pct: float | None
    # Session-count returns (5/21/126/378 trading days back), in percent.
    # Used by the ff_analysis model which was trained on bar-count windows.
    # All None when price history is too short.
    ret_5b_pct:   float | None = None
    ret_21b_pct:  float | None = None
    ret_126b_pct: float | None = None
    ret_378b_pct: float | None = None


class ETFGroup(BaseModel):
    name: str
    etfs: list[ETFPerformance]


class MarketOverviewResult(BaseModel):
    groups: list[ETFGroup]
    fetched_at: str


# ── helpers ───────────────────────────────────────────────────────────────────

def _price_at(valid: list[tuple[int, float]], target: date) -> float | None:
    """Last available closing price on or before target date."""
    target_ts = int(datetime(target.year, target.month, target.day, tzinfo=timezone.utc).timestamp())
    result: float | None = None
    for ts, price in valid:
        if ts <= target_ts:
            result = price
        else:
            break
    return result


def _pct(current: float, past: float | None) -> float | None:
    if past is None or past == 0:
        return None
    return round((current - past) / past * 100, 2)


def _compute(meta: dict, timestamps: list[int], closes: list[float | None]) -> ETFPerformance:
    symbol = meta.get("symbol", "")

    valid: list[tuple[int, float]] = [
        (ts, p) for ts, p in zip(timestamps, closes)
        if p is not None and p > 0
    ]

    if not valid:
        return ETFPerformance(
            symbol=symbol, name=_NAME_MAP.get(symbol, symbol),
            today_pct=None, five_day_pct=None, one_month_pct=None,
            ytd_pct=None, one_year_pct=None, three_year_pct=None,
        )

    current = valid[-1][1]  # last close == regularMarketPrice
    today = date.today()

    # Today: last close vs second-to-last close (previous session)
    today_pct   = _pct(current, valid[-2][1] if len(valid) >= 2 else None)
    five_day    = _pct(current, valid[-6][1] if len(valid) >= 6 else None)
    one_month   = _pct(current, _price_at(valid, today - timedelta(days=30)))
    ytd         = _pct(current, _price_at(valid, date(today.year, 1, 1)))
    one_year    = _pct(current, _price_at(valid, today - timedelta(days=365)))
    three_year  = _pct(current, _price_at(valid, today - timedelta(days=3 * 365)))

    # Session-count returns (trading-day windows) for the ff_analysis model.
    def _bar_ret(n: int) -> float | None:
        if len(valid) > n:
            past = valid[-1 - n][1]
            return _pct(current, past)
        return None

    return ETFPerformance(
        symbol=symbol,
        name=_NAME_MAP.get(symbol, symbol),
        today_pct=today_pct,
        five_day_pct=five_day,
        one_month_pct=one_month,
        ytd_pct=ytd,
        one_year_pct=one_year,
        three_year_pct=three_year,
        ret_5b_pct=_bar_ret(5),
        ret_21b_pct=_bar_ret(21),
        ret_126b_pct=_bar_ret(126),
        ret_378b_pct=_bar_ret(378),
    )


# ── public API ────────────────────────────────────────────────────────────────

class MarketOverviewNode(ScrapingNode):
    def scrape(self) -> MarketOverviewResult | None:
        return scrape_market_overview()


_BATCH_SIZE = 20  # spark endpoint limit


def _fetch_batch(session: cf_requests.Session, symbols: list[str], timeout: int) -> dict[str, ETFPerformance]:
    resp = session.get(
        _SPARK_URL,
        headers=_HEADERS,
        params={
            "symbols": ",".join(symbols),
            "range": "3y",
            "interval": "1d",
            "includePrePost": "false",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    result: dict[str, ETFPerformance] = {}
    for entry in resp.json().get("spark", {}).get("result", []) or []:
        symbol = entry.get("symbol", "")
        responses = entry.get("response") or []
        if not responses:
            continue
        r = responses[0]
        meta = r.get("meta", {})
        timestamps = r.get("timestamp") or []
        closes = (r.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        result[symbol] = _compute(meta, timestamps, closes)
    return result


def scrape_market_overview(timeout: int = 30) -> MarketOverviewResult:
    session = cf_requests.Session(impersonate="chrome124")

    perf_by_symbol: dict[str, ETFPerformance] = {}
    for i in range(0, len(_ALL_SYMBOLS), _BATCH_SIZE):
        batch = _ALL_SYMBOLS[i : i + _BATCH_SIZE]
        perf_by_symbol.update(_fetch_batch(session, batch, timeout))

    groups = [
        ETFGroup(
            name=group_name,
            etfs=[
                perf_by_symbol.get(sym) or ETFPerformance(
                    symbol=sym, name=name,
                    today_pct=None, five_day_pct=None, one_month_pct=None,
                    ytd_pct=None, one_year_pct=None, three_year_pct=None,
                )
                for sym, name in etfs
            ],
        )
        for group_name, etfs in GROUPS
    ]

    return MarketOverviewResult(
        groups=groups,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
