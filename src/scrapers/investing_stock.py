"""
Scraper for investing.com individual equity pages.

Primary data source : embedded __NEXT_DATA__ JSON (price, technical, forecast,
                      earnings, dividends, peers, ownership, company profile).
Supplementary source: HTML key-stats table (EBITDA, ROE, ROA, RSI, ISIN, …
                      not present in the JSON).
"""

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from src.api.web_fetcher import fetch_html

logger = logging.getLogger(__name__)

# ── helpers ──────────────────────────────────────────────────────────────────

_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12, "p": 1e15}


def _num(s: Any) -> float | None:
    """Parse '140.51 T', '25.7M', '-1.10%', '268,500', 20.8 → float."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(",", "").replace("+", "").rstrip("%")
    if s.lower() in ("-", "", "unlock", "n/a"):
        return None
    m = re.fullmatch(r"(-?\d+\.?\d*)\s*([kKmMbBtTpP])?", s)
    if not m:
        return None
    return float(m.group(1)) * _SUFFIX.get((m.group(2) or "").lower(), 1.0)


def _pdate(s: Any) -> date | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(s[:26], fmt).date()
        except ValueError:
            continue
    return None


def _ebitda_raw(s: str | None) -> float | None:
    """Parse display strings like '140.51 T' or '159.98 B' → raw float."""
    if not s:
        return None
    parts = s.split()
    val = _num(parts[0])
    if val is None:
        return None
    mult = _SUFFIX.get(parts[-1].lower(), 1.0) if len(parts) > 1 else 1.0
    return val * mult


def _signal(raw: str | None) -> str:
    if not raw:
        return "Unlock"
    # strip leading category prefix like "_Currencies_" or "_moving_avarge_tool_"
    cleaned = re.sub(r"^_[A-Za-z]+_", "", raw)
    return cleaned.replace("_", " ").title()


_TIMEFRAME_LABELS: dict[str, str] = {
    "PT1M": "1 Min",
    "PT5M": "5 Min",
    "PT15M": "15 Min",
    "PT30M": "30 Min",
    "PT1H": "1 Hour",
    "PT5H": "5 Hours",
    "P1D": "Daily",
    "P1W": "Weekly",
    "P1M": "Monthly",
}

_PEER_LABELS: dict[str, str] = {
    "pe_ltm": "P/E Ratio (LTM)",
    "peg_ltm": "PEG Ratio",
    "price_to_book": "Price / Book",
    "price_to_sales_ltm": "Price / LTM Sales",
    "upside_analyst_target": "Upside (Analyst Target %)",
    "fair_value_upside": "Fair Value Upside %",
    "marketcap": "Market Cap",
    "total_rev": "Total Revenue",
    "total_rev_growth": "Revenue Growth %",
    "gp": "Gross Profit",
    "net_income": "Net Income",
    "ebitda": "EBITDA",
    "gross_margin": "Gross Margin %",
    "net_margin": "Net Margin %",
    "roe": "Return on Equity %",
    "roa": "Return on Assets %",
}


# ── models ───────────────────────────────────────────────────────────────────

class PriceInfo(BaseModel):
    current: float
    currency: str
    change: float
    change_pct: float
    open: float | None = None
    prev_close: float | None = None
    high: float | None = None
    low: float | None = None
    bid: float | None = None
    ask: float | None = None
    week_52_high: float | None = None
    week_52_low: float | None = None
    volume: int | None = None
    avg_volume_3m: int | None = None
    one_year_change_pct: float | None = None
    is_market_open: bool = False
    last_update_unix_ms: str | None = None


class MovingAverage(BaseModel):
    period: int
    value: float
    signal: str


class TechnicalIndicatorEntry(BaseModel):
    value: str | None = None
    action: str | None = None


class PivotPoints(BaseModel):
    classic: dict[str, float] = Field(default_factory=dict)
    fibonacci: dict[str, float] = Field(default_factory=dict)
    camarilla: dict[str, float] = Field(default_factory=dict)
    woodie: dict[str, float] = Field(default_factory=dict)


class TechnicalAnalysis(BaseModel):
    timeframe_signals: dict[str, str] = Field(default_factory=dict)
    overall_signal: str | None = None
    ma_summary_signal: str | None = None
    indicator_summary_signal: str | None = None
    indicators: dict[str, TechnicalIndicatorEntry] = Field(default_factory=dict)
    moving_averages_simple: list[MovingAverage] = Field(default_factory=list)
    moving_averages_exponential: list[MovingAverage] = Field(default_factory=list)
    pivot_points: PivotPoints = Field(default_factory=PivotPoints)


class KeyStats(BaseModel):
    # From JSON (exact raw values in local currency)
    market_cap_raw: float | None = None
    shares_outstanding: int | None = None
    revenue_raw: float | None = None
    net_income_raw: float | None = None     # EPS × shares (computed)
    eps: float | None = None
    dividend: float | None = None
    dividend_yield_pct: float | None = None
    next_earnings_date: date | None = None
    # Ratios (JSON peerBenchmarks preferred, HTML fallback)
    pe_ratio: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    # HTML-sourced (not in JSON)
    ebitda_display: str | None = None       # e.g. "140.51 T"
    ebitda_raw: float | None = None
    ev_ebitda: float | None = None
    return_on_assets_pct: float | None = None
    return_on_equity_pct: float | None = None
    gross_profit_margin_pct: float | None = None
    beta: float | None = None
    rsi_14: float | None = None
    book_value_per_share: float | None = None
    isin: str | None = None
    net_income_display: str | None = None   # raw display string (units vary)


class AnalystRating(BaseModel):
    firm: str
    analyst: str | None = None
    rating: str
    action: str
    price_target: float | None = None
    prev_price_target: float | None = None
    upside_downside_pct: float | None = None
    rating_date: date | None = None
    article_url: str | None = None


class AnalystForecast(BaseModel):
    consensus: str
    buy_count: int = 0
    hold_count: int = 0
    sell_count: int = 0
    total_analysts: int = 0
    avg_price_target: float
    high_price_target: float
    low_price_target: float
    upside_pct: float
    last_rating_date: date | None = None
    ratings: list[AnalystRating] = Field(default_factory=list)


class EarningsRelease(BaseModel):
    release_date: date | None = None
    eps_actual: float | None = None
    eps_forecast: float | None = None
    eps_surprise_pct: float | None = None
    revenue_actual: float | None = None
    revenue_forecast: float | None = None
    revenue_surprise_pct: float | None = None


class DividendRecord(BaseModel):
    ex_date: date | None = None
    amount: float
    yield_pct: float | None = None
    payment_type: str = ""
    pay_date: date | None = None


class PeerBenchmark(BaseModel):
    metric: str
    label: str
    company: float | None = None
    peers: float | None = None
    sector: float | None = None


class TopHolder(BaseModel):
    name: str
    holder_type: str
    shares_held: int
    pct_of_shares_outstanding: float
    holding_date: date | None = None
    total_value: float | None = None


class OwnershipInfo(BaseModel):
    mutual_funds_pct: float | None = None
    institutional_pct: float | None = None
    public_pct: float | None = None
    top_holders: list[TopHolder] = Field(default_factory=list)


class NewsArticle(BaseModel):
    title: str
    provider: str | None = None
    published_at: str
    url: str | None = None


class RelatedStock(BaseModel):
    symbol: str
    name: str
    price: float
    daily_change_pct: float


class CompanyProfile(BaseModel):
    description: str | None = None
    industry: str | None = None
    sector: str | None = None
    employees: int | None = None
    market: str | None = None


class StockPage(BaseModel):
    url: str
    scraped_at: datetime

    name: str
    symbol: str
    exchange: str | None = None
    currency: str

    price: PriceInfo
    key_stats: KeyStats
    profile: CompanyProfile
    technical: TechnicalAnalysis
    analyst_forecast: AnalystForecast | None = None
    latest_earnings: EarningsRelease | None = None
    next_earnings: EarningsRelease | None = None
    dividends: list[DividendRecord] = Field(default_factory=list)
    peer_benchmarks: list[PeerBenchmark] = Field(default_factory=list)
    ownership: OwnershipInfo = Field(default_factory=OwnershipInfo)
    news: list[NewsArticle] = Field(default_factory=list)
    related_stocks: list[RelatedStock] = Field(default_factory=list)


# ── public API ───────────────────────────────────────────────────────────────

def scrape_investing_stock(url: str, timeout: int = 45) -> StockPage:
    """
    Scrape an investing.com equity page and return a structured StockPage.

    Example::

        page = scrape_investing_stock(
            'https://www.investing.com/equities/apple-computer-inc'
        )
        print(page.price.current, page.analyst_forecast.consensus)
    """
    html = fetch_html(url, timeout=timeout)
    return _parse(html, url)


# ── internal parsing ─────────────────────────────────────────────────────────

def _extract_state(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        raise ValueError("__NEXT_DATA__ not found — investing.com may have changed its structure")
    return json.loads(m.group(1))["props"]["pageProps"]["state"]


def _html_stats(soup: BeautifulSoup) -> dict[str, str]:
    """Parse the key-stats row panel → {label: raw_value_string}.
    Each row uses <dt> for the label and <dd> for the value.
    """
    rows = soup.find_all(
        "div",
        class_=lambda c: c and "border-t-[#e6e9eb]" in c and "flex-wrap" in c,
    )
    out: dict[str, str] = {}
    for row in rows:
        dt = row.find("dt")
        dd = row.find("dd")
        if dt and dd:
            label = dt.get_text(" ", strip=True)
            value = dd.get_text(" ", strip=True)
            if label:
                out[label] = value
    return out


def _parse(html: str, url: str) -> StockPage:
    soup = BeautifulSoup(html, "html.parser")
    state = _extract_state(html)

    inst = state["equityStore"]["instrument"]
    price_data = inst.get("price", {})
    fund = inst.get("fundamental", {})
    vol = inst.get("volume", {})
    bid = inst.get("bidding", {})
    exch = inst.get("exchange", {})
    earn_inst = inst.get("earnings", {})
    relatives = inst.get("relatives", {}).get("relatives", [{}])
    primary = relatives[0] if relatives else {}

    stats_html = _html_stats(soup)

    return StockPage(
        url=url,
        scraped_at=datetime.now(timezone.utc),
        name=price_data.get("long_name") or primary.get("name", ""),
        symbol=primary.get("symbol", ""),
        exchange=exch.get("exchange"),
        currency=price_data.get("currency", ""),
        price=_parse_price(price_data, vol, bid),
        key_stats=_parse_key_stats(fund, vol, earn_inst, state, stats_html),
        profile=_parse_profile(state),
        technical=_parse_technical(inst, state),
        analyst_forecast=_parse_forecast(state),
        latest_earnings=_parse_latest_earnings(state),
        next_earnings=_parse_next_earnings(state),
        dividends=_parse_dividends(state),
        peer_benchmarks=_parse_peers(state),
        ownership=_parse_ownership(state),
        news=_parse_news(soup),
        related_stocks=_parse_related(state),
    )


# ── section parsers ───────────────────────────────────────────────────────────

def _parse_price(p: dict, vol: dict, bid: dict) -> PriceInfo:
    return PriceInfo(
        current=float(p.get("last", 0)),
        currency=p.get("currency", ""),
        change=float(p.get("change", 0)),
        change_pct=float(p.get("changePcr", 0)),
        open=_num(p.get("open")),
        prev_close=_num(p.get("lastClose")),
        high=_num(p.get("high")),
        low=_num(p.get("low")),
        bid=_num(bid.get("bid")),
        ask=_num(bid.get("ask")),
        week_52_high=_num(p.get("fiftyTwoWeekHigh")),
        week_52_low=_num(p.get("fiftyTwoWeekLow")),
        volume=int(p.get("volume", 0)) or None,
        avg_volume_3m=int(vol.get("average", 0)) or None,
        one_year_change_pct=_num(p.get("oneYearChange")),
        is_market_open=p.get("isOpen", False) in (True, "1", 1),
        last_update_unix_ms=str(p.get("lastUpdateTime")) if p.get("lastUpdateTime") else None,
    )


def _parse_key_stats(
    fund: dict,
    vol: dict,
    earn_inst: dict,
    state: dict,
    stats_html: dict[str, str],
) -> KeyStats:
    # Ratios from peer benchmarks (company column is the most reliable JSON source)
    pb_value = state.get("peerBenchmarksStore", {}).get("peerBenchmarksData", {}).get("value", [])
    pb_map: dict[str, float | None] = {
        r["key"]: _num(r.get("company")) for r in pb_value if isinstance(r, dict)
    }

    eps = _num(fund.get("eps"))
    shares = fund.get("sharesOutstanding")
    net_income_raw = (eps * shares) if eps and shares else None

    # Next earnings from equityStore.instrument.earnings
    next_earn_date = _pdate(earn_inst.get("nextReport"))
    # Also try earningsStore
    if not next_earn_date:
        nr = state.get("earningsStore", {}).get("keyMetrics", {}).get("next_release", {})
        next_earn_date = _pdate(nr.get("date"))

    # HTML-sourced stats — labels are now full strings like "Return on Equity"
    def _h(label: str) -> str | None:
        return stats_html.get(label)

    def _hn(label: str) -> float | None:
        v = _h(label)
        return _num(v.split()[0]) if v else None

    ebitda_str = _h("EBITDA")
    ev_ebitda_str = _h("EV/EBITDA")
    rsi_str = _h("RSI(14)")
    pe_html = _hn("P/E Ratio")

    roe_val = _num((_h("Return on Equity") or "").replace("%", "").strip() or None)
    roa_val = _num((_h("Return on Assets") or "").replace("%", "").strip() or None)
    gpm_val = _num((_h("Gross Profit Margin") or "").replace("%", "").strip() or None)

    return KeyStats(
        market_cap_raw=_num(fund.get("marketCapRaw")),
        shares_outstanding=int(shares) if shares else None,
        revenue_raw=_num(fund.get("revenueRaw")),
        net_income_raw=net_income_raw,
        eps=eps,
        dividend=_num(fund.get("dividend")),
        dividend_yield_pct=_num(fund.get("yield")),
        next_earnings_date=next_earn_date,
        pe_ratio=pb_map.get("pe_ltm") or pe_html,
        peg_ratio=pb_map.get("peg_ltm"),
        price_to_book=pb_map.get("price_to_book"),
        price_to_sales=pb_map.get("price_to_sales_ltm"),
        ebitda_display=ebitda_str,
        ebitda_raw=_ebitda_raw(ebitda_str),
        ev_ebitda=_num(ev_ebitda_str) if ev_ebitda_str else None,
        return_on_equity_pct=roe_val,
        return_on_assets_pct=roa_val,
        gross_profit_margin_pct=gpm_val,
        beta=_num(stats_html.get("Beta")),
        rsi_14=_num(rsi_str) if rsi_str else None,
        book_value_per_share=_num(stats_html.get("Book Value / Share")),
        isin=stats_html.get("ISIN"),
        net_income_display=_h("Net Income"),
    )


def _parse_profile(state: dict) -> CompanyProfile:
    p = state.get("companyProfileStore", {}).get("profile", {})
    return CompanyProfile(
        description=p.get("description"),
        industry=p.get("industry", {}).get("name") if isinstance(p.get("industry"), dict) else p.get("industry"),
        sector=p.get("sector", {}).get("name") if isinstance(p.get("sector"), dict) else p.get("sector"),
        employees=p.get("employees"),
        market=p.get("market", {}).get("name") if isinstance(p.get("market"), dict) else p.get("market"),
    )


def _parse_technical(inst: dict, state: dict) -> TechnicalAnalysis:
    tf_raw: dict[str, str] = inst.get("technical", {}).get("summary", {})
    timeframe_signals = {
        _TIMEFRAME_LABELS.get(k, k): _signal(v) for k, v in tf_raw.items()
    }
    overall = timeframe_signals.get("Daily")

    td = state.get("technicalStore", {}).get("technicalData", {})

    # Indicators
    ind_raw = td.get("indicators", {})
    indicators: dict[str, TechnicalIndicatorEntry] = {}
    for key, val in ind_raw.items():
        if isinstance(val, dict) and key != "summary":
            indicators[key] = TechnicalIndicatorEntry(
                value=str(val.get("value")) if val.get("value") is not None else None,
                action=val.get("action"),
            )
    ind_summary = ind_raw.get("summary", {})

    # Moving averages
    def _parse_mas(ma_dict: dict, prefix: str) -> list[MovingAverage]:
        mas: list[MovingAverage] = []
        for period in (5, 10, 20, 50, 100, 200):
            val_key = f"{prefix}{period}"
            sig_key = f"MA{period}{'EBS' if 'EMA' in prefix else 'BS'}"
            if val_key in ma_dict:
                v = _num(ma_dict[val_key])
                if v is not None:
                    mas.append(MovingAverage(
                        period=period,
                        value=v,
                        signal=ma_dict.get(sig_key, ""),
                    ))
        return mas

    ma_data = td.get("movingAverages", {})
    sma = _parse_mas(ma_data.get("simple", {}), "SMA")
    ema = _parse_mas(ma_data.get("exponential", {}), "EMA")
    ma_summary = ma_data.get("summary", {}).get("value", "")

    # Pivot points
    pp_raw = td.get("pivotPoints", {})
    pivots = PivotPoints(
        classic={k: float(v) for k, v in {
            "pivot": pp_raw.get("pivot"),
            "s1": pp_raw.get("s1"), "s2": pp_raw.get("s2"), "s3": pp_raw.get("s3"),
            "r1": pp_raw.get("r1"), "r2": pp_raw.get("r2"), "r3": pp_raw.get("r3"),
        }.items() if v is not None},
        fibonacci={k: float(v) for k, v in {
            "pivot": pp_raw.get("pivot"),
            "s1": pp_raw.get("s1Fib"), "s2": pp_raw.get("s2Fib"), "s3": pp_raw.get("s3Fib"),
            "r1": pp_raw.get("r1Fib"), "r2": pp_raw.get("r2Fib"), "r3": pp_raw.get("r3Fib"),
        }.items() if v is not None},
        camarilla={k: float(v) for k, v in {
            "s1": pp_raw.get("cs1"), "s2": pp_raw.get("cs2"), "s3": pp_raw.get("cs3"),
            "r1": pp_raw.get("cr1"), "r2": pp_raw.get("cr2"), "r3": pp_raw.get("cr3"),
        }.items() if v is not None},
        woodie={k: float(v) for k, v in {
            "pivot": pp_raw.get("pivotWo"),
            "s1": pp_raw.get("s1Wo"), "s2": pp_raw.get("s2Wo"), "s3": pp_raw.get("s3Wo"),
            "r1": pp_raw.get("r1Wo"), "r2": pp_raw.get("r2Wo"), "r3": pp_raw.get("r3Wo"),
        }.items() if v is not None},
    )

    return TechnicalAnalysis(
        timeframe_signals=timeframe_signals,
        overall_signal=overall,
        ma_summary_signal=_signal(ma_summary),
        indicator_summary_signal=_signal(ind_summary.get("value")),
        indicators=indicators,
        moving_averages_simple=sma,
        moving_averages_exponential=ema,
        pivot_points=pivots,
    )


def _parse_forecast(state: dict) -> AnalystForecast | None:
    fc = state.get("forecastStore", {})
    f = fc.get("forecast")
    if not f:
        return None

    ratings_raw = fc.get("ratings", [])
    ratings = [
        AnalystRating(
            firm=r.get("firm_name", ""),
            analyst=r.get("analyst_name"),
            rating=r.get("rating_translated", r.get("rating", "")),
            action=r.get("action_translated", r.get("action", "")),
            price_target=_num(r.get("price_target")),
            prev_price_target=_num(r.get("past_price_target")),
            upside_downside_pct=_num(r.get("upside_downside")),
            rating_date=_pdate(r.get("date")),
            article_url=r.get("articleHref"),
        )
        for r in ratings_raw
        if isinstance(r, dict)
    ]

    return AnalystForecast(
        consensus=f.get("consensus_recommendation", "").replace("_", " ").title(),
        buy_count=int(f.get("number_of_analysts_buy", 0)),
        hold_count=int(f.get("number_of_analysts_hold", 0)),
        sell_count=int(f.get("number_of_analysts_sell", 0)),
        total_analysts=int(f.get("number_of_estimates", 0)),
        avg_price_target=float(f.get("target_price_consensus_mean", 0)),
        high_price_target=float(f.get("target_price_consensus_high", 0)),
        low_price_target=float(f.get("target_price_consensus_low", 0)),
        upside_pct=float(f.get("upside_percent", 0)),
        last_rating_date=_pdate(f.get("last_rating_date")),
        ratings=ratings,
    )


def _parse_earnings_release(raw: dict) -> EarningsRelease:
    return EarningsRelease(
        release_date=_pdate(raw.get("date")),
        eps_actual=_num(raw.get("eps_actual")),
        eps_forecast=_num(raw.get("eps_forecast")),
        eps_surprise_pct=_num(raw.get("eps_surprise")),
        revenue_actual=_num(raw.get("revenue_actual")),
        revenue_forecast=_num(raw.get("revenue_forecast")),
        revenue_surprise_pct=_num(raw.get("revenue_surprise")),
    )


def _parse_latest_earnings(state: dict) -> EarningsRelease | None:
    raw = state.get("earningsStore", {}).get("keyMetrics", {}).get("latest_release")
    return _parse_earnings_release(raw) if raw else None


def _parse_next_earnings(state: dict) -> EarningsRelease | None:
    raw = state.get("earningsStore", {}).get("keyMetrics", {}).get("next_release")
    return _parse_earnings_release(raw) if raw else None


def _parse_dividends(state: dict) -> list[DividendRecord]:
    out = []
    for d in state.get("dividendsStore", {}).get("equityDividends", []):
        if not isinstance(d, dict):
            continue
        out.append(DividendRecord(
            ex_date=_pdate(d.get("div_date")),
            amount=float(d.get("div_amount", 0)),
            yield_pct=_num(d.get("yield")),
            payment_type=d.get("div_payment_type", ""),
            pay_date=_pdate(d.get("pay_date")),
        ))
    return out


def _parse_peers(state: dict) -> list[PeerBenchmark]:
    pb = state.get("peerBenchmarksStore", {}).get("peerBenchmarksData", {})
    benchmarks: list[PeerBenchmark] = []
    for category_rows in pb.values():
        if not isinstance(category_rows, list):
            continue
        for row in category_rows:
            if not isinstance(row, dict):
                continue
            key = row.get("key", "")
            benchmarks.append(PeerBenchmark(
                metric=key,
                label=_PEER_LABELS.get(key, key.replace("_", " ").title()),
                company=_num(row.get("company")),
                peers=_num(row.get("peers")),
                sector=_num(row.get("sector")),
            ))
    return benchmarks


def _parse_ownership(state: dict) -> OwnershipInfo:
    own = state.get("ownershipStore", {})

    holders: list[TopHolder] = []
    for source_key in ("institutionalData", "mutualFundData"):
        for h in own.get(source_key, {}).get(
            "institutionalOwners" if source_key == "institutionalData" else "mutualFundOwners", []
        ):
            if not isinstance(h, dict):
                continue
            holders.append(TopHolder(
                name=h.get("owner_name", ""),
                holder_type=h.get("holder_type", h.get("company_type_name", "")),
                shares_held=int(h.get("shares_held", 0)),
                pct_of_shares_outstanding=float(h.get("percent_of_shares_outstanding", 0)),
                holding_date=_pdate(h.get("holding_date")),
                total_value=_num(h.get("total_value")),
            ))

    # Sort by % held descending, keep top 20
    holders.sort(key=lambda h: h.pct_of_shares_outstanding, reverse=True)

    # Ownership composition percentages
    mf_pct: float | None = None
    inst_pct: float | None = None
    pub_pct: float | None = None
    comp = own.get("compositionData", own.get("ownershipComposition", {}))
    if isinstance(comp, dict):
        for k, v in comp.items():
            kl = k.lower()
            if "mutual" in kl or "etf" in kl:
                mf_pct = _num(v)
            elif "institutional" in kl:
                inst_pct = _num(v)
            elif "public" in kl or "retail" in kl:
                pub_pct = _num(v)

    return OwnershipInfo(
        mutual_funds_pct=mf_pct,
        institutional_pct=inst_pct,
        public_pct=pub_pct,
        top_holders=holders[:20],
    )


def _parse_news(soup: BeautifulSoup) -> list[NewsArticle]:
    articles = []
    for el in soup.find_all(attrs={"data-test": "article-item"}):
        title_el = el.find(attrs={"data-test": "article-title-link"})
        prov_el = el.find(attrs={"data-test": "article-provider-link"})
        date_el = el.find(attrs={"data-test": "article-publish-date"})
        if not title_el:
            continue
        # Provider may be a linked element (Investing.com) or a plain span (Reuters etc.)
        provider: str | None = None
        if prov_el:
            provider = prov_el.get_text(strip=True)
        else:
            # Fallback: look for short non-date span near the article header
            for span in el.find_all("span"):
                t = span.get_text(strip=True)
                if t and len(t) < 40 and not re.search(r"\d{4}|ago|hour|min|day", t, re.I):
                    provider = t
                    break
        href = title_el.get("href", "") if hasattr(title_el, "get") else ""
        articles.append(NewsArticle(
            title=title_el.get_text(strip=True),
            provider=provider,
            published_at=date_el.get_text(strip=True) if date_el else "",
            url=f"https://www.investing.com{href}" if href and href.startswith("/") else (href or None),
        ))
    return articles


def _parse_related(state: dict) -> list[RelatedStock]:
    out = []
    for r in state.get("peopleAlsoWatchStore", {}).get("benchMarksV2", []):
        if not isinstance(r, dict):
            continue
        out.append(RelatedStock(
            symbol=r.get("symbol", ""),
            name=r.get("shortname_translated", ""),
            price=float(r.get("current_price", 0)),
            daily_change_pct=float(r.get("daily_change_pct", 0)),
        ))
    return out
