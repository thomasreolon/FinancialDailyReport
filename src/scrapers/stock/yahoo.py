"""
Yahoo Finance comprehensive stock profile — 3 API calls + 2 DOM-scraped pages
+ 1 chart call (no auth) for 3y of daily closes used for return/vol features.

Call 1 (core):       price, assetProfile, summaryDetail, defaultKeyStatistics, financialData
Call 2 (financials): incomeStatementHistory(+Quarterly)
Call 3 (analysis):   earningsTrend, earningsHistory, recommendationTrend
DOM /balance-sheet/: total assets, liabilities, equity, debt, working capital, etc.
DOM /cash-flow/:     operating/investing/financing CF, capex, FCF, buybacks, etc.
Chart /v8/finance/chart/SYMBOL: 3y of 1d closes (separate curl_cffi call,
                     wrapped in try/except so price-history failure leaves the
                     derived fields null but does not break the broader scrape).

Balance sheet and cash flow use DOM scraping because Yahoo's quoteSummary API
no longer returns populated fields for those modules.
All DOM values are displayed in thousands — multiplied by 1000 in parsing.
"""

import math
from datetime import datetime, timezone

from curl_cffi import requests as cf_requests
from pydantic import BaseModel, Field

from src.scrapers.base import ScrapingNode

_BASE = "https://query1.finance.yahoo.com"
_CRUMB_URL = f"{_BASE}/v1/test/getcrumb"
_SUMMARY_URL = f"{_BASE}/v10/finance/quoteSummary/{{symbol}}"
_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
    "Accept": "application/json",
}

_MODULES_CORE = "price,assetProfile,summaryDetail,defaultKeyStatistics,financialData"
_MODULES_FINANCIALS = "incomeStatementHistory,incomeStatementHistoryQuarterly"
_MODULES_ANALYSIS = "earningsTrend,earningsHistory,recommendationTrend"

_JS_EXTRACT_TABLE = """() => {
    const section = document.querySelector('[data-testid="qsp-financials"]');
    if (!section) return {dates: [], rows: {}};
    const headerCols = section.querySelectorAll('.tableHeader .column:not(.sticky)');
    const dates = Array.from(headerCols).map(c => c.innerText.trim());
    const rows = {};
    for (const row of section.querySelectorAll('.tableBody .row')) {
        const titleEl = row.querySelector('.rowTitle');
        if (!titleEl) continue;
        const title = titleEl.innerText.trim();
        const valCols = row.querySelectorAll('.column:not(.sticky)');
        rows[title] = Array.from(valCols).map(c => c.innerText.trim());
    }
    return {dates, rows};
}"""

_BS_LABEL_MAP = {
    "Total Assets": "total_assets",
    "Total Liabilities Net Minority Interest": "total_liabilities",
    "Total Equity Gross Minority Interest": "total_equity",
    "Total Debt": "total_debt",
    "Net Debt": "net_debt",
    "Working Capital": "working_capital",
    "Invested Capital": "invested_capital",
    "Share Issued": "shares_issued",
}

_CF_LABEL_MAP = {
    "Operating Cash Flow": "operating_cash_flow",
    "Investing Cash Flow": "investing_cash_flow",
    "Financing Cash Flow": "financing_cash_flow",
    "Capital Expenditure": "capital_expenditures",
    "Free Cash Flow": "free_cash_flow",
    "Repurchase of Capital Stock": "repurchase_of_stock",
    "End Cash Position": "end_cash_position",
}


def _fetch_all_via_playwright(symbol: str, timeout: int) -> tuple[dict, dict, dict, dict, dict]:
    """
    Open one Playwright session, handle GDPR consent, make 3 API calls via
    credentials:'include', then scrape balance-sheet and cash-flow pages from the DOM.
    Returns (core, fin, anl, bs_dom, cf_dom).
    """
    from playwright.sync_api import sync_playwright

    def _api_call(page, modules: str, crumb: str) -> dict:
        js = f"""async () => {{
            const url = new URL('https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}');
            url.searchParams.set('modules', '{modules}');
            url.searchParams.set('crumb', '{crumb}');
            url.searchParams.set('lang', 'en-US');
            url.searchParams.set('region', 'US');
            const r = await fetch(url.toString(), {{
                credentials: 'include',
                headers: {{'Accept': 'application/json'}}
            }});
            return r.json();
        }}"""
        data = page.evaluate(js)
        err = (data.get("quoteSummary") or {}).get("error")
        if err:
            raise RuntimeError(f"Yahoo API error ({modules[:30]}): {err}")
        results = (data.get("quoteSummary") or {}).get("result") or []
        return results[0] if results else {}

    def _scrape_dom_page(page, url: str) -> dict:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1_000)
        try:
            page.wait_for_selector(
                '[data-testid="qsp-financials"] .tableBody .row',
                timeout=15_000,
            )
        except Exception:
            pass
        return page.evaluate(_JS_EXTRACT_TABLE) or {"dates": [], "rows": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = ctx.new_page()
        page.goto("https://finance.yahoo.com/", wait_until="domcontentloaded", timeout=timeout * 1_000)

        if "consent.yahoo.com" in page.url:
            try:
                page.click("button[name='agree']", timeout=8_000)
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:
                pass

        crumb = page.evaluate(
            "async () => { const r = await fetch('https://query1.finance.yahoo.com/v1/test/getcrumb', {credentials: 'include'}); return r.text(); }"
        ).strip()

        core = _api_call(page, _MODULES_CORE, crumb)
        fin  = _api_call(page, _MODULES_FINANCIALS, crumb)
        anl  = _api_call(page, _MODULES_ANALYSIS, crumb)

        base = f"https://finance.yahoo.com/quote/{symbol}"
        bs_dom = _scrape_dom_page(page, f"{base}/balance-sheet/")
        cf_dom = _scrape_dom_page(page, f"{base}/cash-flow/")

        browser.close()

    return core, fin, anl, bs_dom, cf_dom


# ── helpers ───────────────────────────────────────────────────────────────────

def _r(d: dict | None, key: str) -> float | None:
    if not d:
        return None
    v = d.get(key)
    if isinstance(v, dict):
        raw = v.get("raw")
        return float(raw) if raw is not None else None
    return float(v) if isinstance(v, (int, float)) else None


def _f(d: dict | None, key: str) -> str | None:
    if not d:
        return None
    v = d.get(key)
    if isinstance(v, dict):
        return v.get("fmt") or None
    return str(v) if isinstance(v, str) and v else None


def _pct(d: dict | None, key: str) -> float | None:
    v = _r(d, key)
    return round(v * 100, 4) if v is not None else None


def _period_date(entry: dict) -> str | None:
    ed = entry.get("endDate")
    if isinstance(ed, dict):
        return ed.get("fmt")
    return str(ed) if ed else None


# ── models ────────────────────────────────────────────────────────────────────

class Officer(BaseModel):
    name: str | None
    title: str | None
    age: int | None


class IncomeStatement(BaseModel):
    period: str
    total_revenue: float | None
    cost_of_revenue: float | None
    gross_profit: float | None
    research_development: float | None
    sga: float | None
    operating_income: float | None
    ebit: float | None
    interest_expense: float | None
    net_income: float | None
    diluted_eps: float | None


class BalanceSheet(BaseModel):
    period: str
    total_assets: float | None
    total_liabilities: float | None
    total_equity: float | None
    total_debt: float | None
    net_debt: float | None
    working_capital: float | None
    invested_capital: float | None
    shares_issued: float | None


class CashFlowStatement(BaseModel):
    period: str
    operating_cash_flow: float | None
    investing_cash_flow: float | None
    financing_cash_flow: float | None
    capital_expenditures: float | None
    free_cash_flow: float | None
    repurchase_of_stock: float | None
    end_cash_position: float | None


class EarningsEstimate(BaseModel):
    period: str          # "0q" current qtr, "+1q" next qtr, "0y" current yr, "+1y" next yr
    end_date: str | None
    avg_eps: float | None
    low_eps: float | None
    high_eps: float | None
    num_analysts_eps: int | None
    year_ago_eps: float | None
    eps_growth: float | None
    avg_revenue: float | None
    low_revenue: float | None
    high_revenue: float | None
    num_analysts_revenue: int | None
    year_ago_revenue: float | None
    revenue_growth: float | None
    eps_trend_current: float | None
    eps_trend_7d_ago: float | None
    eps_trend_30d_ago: float | None
    eps_trend_60d_ago: float | None
    eps_trend_90d_ago: float | None
    eps_revisions_up_7d: int | None
    eps_revisions_up_30d: int | None
    eps_revisions_down_30d: int | None


class EarningsHistoryEntry(BaseModel):
    quarter: str | None
    eps_estimate: float | None
    eps_actual: float | None
    eps_difference: float | None
    surprise_pct: float | None


class RecommendationSnapshot(BaseModel):
    period: str           # "0m" = current month, "-1m" = last month, etc.
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


class YahooProfile(BaseModel):
    symbol: str

    # ── identity ──────────────────────────────────────────────────────────────
    name: str | None
    exchange: str | None
    currency: str | None
    sector: str | None
    industry: str | None
    description: str | None
    employees: int | None
    website: str | None
    officers: list[Officer] = Field(default_factory=list)

    # ── price snapshot ────────────────────────────────────────────────────────
    price: float | None
    change_pct: float | None
    market_cap: float | None
    volume: int | None
    avg_volume: int | None
    week_52_high: float | None
    week_52_low: float | None
    beta: float | None

    # ── valuation ratios ──────────────────────────────────────────────────────
    pe_ratio: float | None
    forward_pe: float | None
    peg_ratio: float | None
    eps: float | None
    dividend_yield_pct: float | None
    enterprise_value: float | None
    ev_revenue: float | None
    ev_ebitda: float | None

    # ── profitability ─────────────────────────────────────────────────────────
    profit_margin_pct: float | None
    operating_margin_pct: float | None
    return_on_equity_pct: float | None
    return_on_assets_pct: float | None
    gross_margin_pct: float | None

    # ── financials (TTM) ──────────────────────────────────────────────────────
    revenue: float | None
    ebitda: float | None
    net_income: float | None
    free_cash_flow: float | None
    total_cash: float | None
    total_debt: float | None

    # ── ownership / float ─────────────────────────────────────────────────────
    short_ratio: float | None
    short_pct_of_float: float | None
    insider_pct: float | None
    institution_pct: float | None
    shares_outstanding: float | None

    # ── income statements (annual then quarterly, newest first) ───────────────
    income_annual: list[IncomeStatement] = Field(default_factory=list)
    income_quarterly: list[IncomeStatement] = Field(default_factory=list)

    # ── balance sheets ────────────────────────────────────────────────────────
    balance_annual: list[BalanceSheet] = Field(default_factory=list)
    balance_quarterly: list[BalanceSheet] = Field(default_factory=list)

    # ── cash flow statements ──────────────────────────────────────────────────
    cashflow_annual: list[CashFlowStatement] = Field(default_factory=list)
    cashflow_quarterly: list[CashFlowStatement] = Field(default_factory=list)

    # ── earnings estimates (current qtr → next year) ──────────────────────────
    earnings_estimates: list[EarningsEstimate] = Field(default_factory=list)

    # ── earnings beat/miss history (last 4 quarters) ──────────────────────────
    earnings_history: list[EarningsHistoryEntry] = Field(default_factory=list)

    # ── analyst recommendation trend (last 4 months) ──────────────────────────
    recommendation_trend: list[RecommendationSnapshot] = Field(default_factory=list)

    # ── price-history derived features (session-count windows) ────────────────
    # All None if the price-history fetch failed. Returns are in percent.
    ret_1d_pct:   float | None = None
    ret_5d_pct:   float | None = None
    ret_21d_pct:  float | None = None
    ret_42d_pct:  float | None = None
    ret_126d_pct: float | None = None
    ret_252d_pct: float | None = None
    vol_21d_pct:  float | None = None     # annualized stdev of last 21 log-returns, %
    price_norm_d0: float | None = None    # close[-1] / close[-11]
    price_norm_d1: float | None = None    # close[-2] / close[-12]
    price_norm_d2: float | None = None
    price_norm_d3: float | None = None
    price_norm_d4: float | None = None
    price_norm_d5: float | None = None
    price_norm_d6: float | None = None
    price_norm_d7: float | None = None
    price_norm_d8: float | None = None
    price_norm_d9: float | None = None
    years_listed: float | None = None     # days since first trade / 365.25
    first_trade_date: str | None = None   # ISO date


# ── parsing helpers ───────────────────────────────────────────────────────────

def _parse_income(entry: dict) -> IncomeStatement:
    return IncomeStatement(
        period=_period_date(entry) or "",
        total_revenue=_r(entry, "totalRevenue"),
        cost_of_revenue=_r(entry, "costOfRevenue"),
        gross_profit=_r(entry, "grossProfit"),
        research_development=_r(entry, "researchDevelopment"),
        sga=_r(entry, "sellingGeneralAdministrative"),
        operating_income=_r(entry, "operatingIncome"),
        ebit=_r(entry, "ebit"),
        interest_expense=_r(entry, "interestExpense"),
        net_income=_r(entry, "netIncome"),
        diluted_eps=_r(entry, "dilutedEps"),
    )


def _dom_val(rows: dict, label: str, i: int) -> float | None:
    vals = rows.get(label, [])
    if i >= len(vals):
        return None
    v = vals[i].replace(",", "").replace("--", "").strip()
    return float(v) * 1_000 if v else None


def _parse_dom_balance(dom: dict) -> list[BalanceSheet]:
    dates = dom.get("dates", [])
    rows = dom.get("rows", {})
    result = []
    for i, date in enumerate(dates):
        fields: dict = {"period": date}
        for label, field in _BS_LABEL_MAP.items():
            fields[field] = _dom_val(rows, label, i)
        result.append(BalanceSheet(**fields))
    return result


def _parse_dom_cashflow(dom: dict) -> list[CashFlowStatement]:
    dates = dom.get("dates", [])
    rows = dom.get("rows", {})
    result = []
    for i, date in enumerate(dates):
        fields: dict = {"period": date}
        for label, field in _CF_LABEL_MAP.items():
            fields[field] = _dom_val(rows, label, i)
        result.append(CashFlowStatement(**fields))
    return result


def _parse_estimate(t: dict) -> EarningsEstimate:
    ee = t.get("earningsEstimate", {})
    re_ = t.get("revenueEstimate", {})
    et = t.get("epsTrend", {})
    er = t.get("epsRevisions", {})
    return EarningsEstimate(
        period=t.get("period", ""),
        end_date=t.get("endDate") or None,
        avg_eps=_r(ee, "avg"),
        low_eps=_r(ee, "low"),
        high_eps=_r(ee, "high"),
        num_analysts_eps=int(_r(ee, "numberOfAnalysts") or 0) or None,
        year_ago_eps=_r(ee, "yearAgoEps"),
        eps_growth=_pct(ee, "growth"),
        avg_revenue=_r(re_, "avg"),
        low_revenue=_r(re_, "low"),
        high_revenue=_r(re_, "high"),
        num_analysts_revenue=int(_r(re_, "numberOfAnalysts") or 0) or None,
        year_ago_revenue=_r(re_, "yearAgoRevenue"),
        revenue_growth=_pct(re_, "growth"),
        eps_trend_current=_r(et, "current"),
        eps_trend_7d_ago=_r(et, "7daysAgo"),
        eps_trend_30d_ago=_r(et, "30daysAgo"),
        eps_trend_60d_ago=_r(et, "60daysAgo"),
        eps_trend_90d_ago=_r(et, "90daysAgo"),
        eps_revisions_up_7d=int(_r(er, "upLast7days") or 0) or None,
        eps_revisions_up_30d=int(_r(er, "upLast30days") or 0) or None,
        eps_revisions_down_30d=int(_r(er, "downLast30days") or 0) or None,
    )


# ── price-history fetch (chart API, no auth) ──────────────────────────────────

def _fetch_price_history(symbol: str, timeout: int = 30) -> tuple[list[int], list[float | None], int | None]:
    """
    Fetch ~3y of daily closes via the public chart endpoint (no crumb needed).
    Returns (timestamps, closes, first_trade_date_epoch). Empty/None on failure.
    """
    try:
        session = cf_requests.Session(impersonate="chrome124")
        resp = session.get(
            _CHART_URL.format(symbol=symbol),
            headers=_HEADERS,
            params={"interval": "1d", "range": "3y", "includePrePost": "false"},
            timeout=timeout,
        )
        resp.raise_for_status()
        result = (resp.json().get("chart", {}).get("result") or [None])[0]
        if not result:
            return [], [], None
        meta = result.get("meta") or {}
        timestamps = result.get("timestamp") or []
        closes = ((result.get("indicators", {}).get("quote") or [{}])[0].get("close") or [])
        first_trade = meta.get("firstTradeDate") or meta.get("firstTradeDateEpochUtc")
        return timestamps, closes, first_trade
    except Exception:
        return [], [], None


def _price_features(timestamps: list[int], closes: list[float | None], first_trade_epoch: int | None) -> dict:
    """Compute session-count return / volatility / price_norm / years_listed features."""
    valid: list[float] = [c for c in closes if c is not None and c > 0]
    out: dict = {
        "ret_1d_pct": None, "ret_5d_pct": None, "ret_21d_pct": None,
        "ret_42d_pct": None, "ret_126d_pct": None, "ret_252d_pct": None,
        "vol_21d_pct": None,
        "first_trade_date": None, "years_listed": None,
    }
    for k in range(10):
        out[f"price_norm_d{k}"] = None

    if len(valid) >= 2:
        current = valid[-1]
        for horizon, key in [(1, "ret_1d_pct"), (5, "ret_5d_pct"), (21, "ret_21d_pct"),
                             (42, "ret_42d_pct"), (126, "ret_126d_pct"), (252, "ret_252d_pct")]:
            if len(valid) > horizon:
                past = valid[-1 - horizon]
                if past > 0:
                    out[key] = round((current - past) / past * 100.0, 4)

    # vol_21d: annualized stdev of last 21 daily log-returns (in %)
    if len(valid) >= 22:
        tail = valid[-22:]
        rets = [math.log(tail[i] / tail[i - 1]) for i in range(1, 22) if tail[i - 1] > 0]
        if len(rets) >= 2:
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            out["vol_21d_pct"] = round(math.sqrt(var) * math.sqrt(252) * 100.0, 4)

    # price_norm_d{k}: close[-1-k] / close[-11-k] for k in 0..9
    for k in range(10):
        if len(valid) > 11 + k:
            denom = valid[-11 - k]
            if denom > 0:
                out[f"price_norm_d{k}"] = round(valid[-1 - k] / denom, 6)

    if first_trade_epoch:
        try:
            d0 = datetime.fromtimestamp(int(first_trade_epoch), tz=timezone.utc).date()
            out["first_trade_date"] = d0.isoformat()
            out["years_listed"] = round(
                (datetime.now(timezone.utc).date() - d0).days / 365.25, 3
            )
        except (ValueError, OSError, OverflowError):
            pass
    elif timestamps:
        try:
            d0 = datetime.fromtimestamp(int(timestamps[0]), tz=timezone.utc).date()
            out["years_listed"] = round(
                (datetime.now(timezone.utc).date() - d0).days / 365.25, 3
            )
        except (ValueError, OSError, OverflowError):
            pass

    return out


# ── public API ────────────────────────────────────────────────────────────────

class YahooProfileNode(ScrapingNode):
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()

    def scrape(self) -> YahooProfile | None:
        return scrape_yahoo_profile(self.symbol)


def scrape_yahoo_profile(symbol: str, timeout: int = 120) -> YahooProfile:
    symbol = symbol.upper()
    core, fin, analysis, bs_dom, cf_dom = _fetch_all_via_playwright(symbol, timeout)
    ts, closes, first_trade_epoch = _fetch_price_history(symbol)
    px_feat = _price_features(ts, closes, first_trade_epoch)

    price_m = core.get("price", {})
    profile_m = core.get("assetProfile", {})
    detail_m = core.get("summaryDetail", {})
    stats_m = core.get("defaultKeyStatistics", {})
    fin_m = core.get("financialData", {})

    officers = [
        Officer(name=o.get("name"), title=o.get("title"), age=o.get("age"))
        for o in profile_m.get("companyOfficers", [])
    ]

    def _income_list(key_outer: str, key_inner: str) -> list[IncomeStatement]:
        return [_parse_income(e) for e in fin.get(key_outer, {}).get(key_inner, [])]

    # earnings estimates (only the 4 forward periods, skip "+5y"/"-5y")
    trend_entries = [
        _parse_estimate(t)
        for t in analysis.get("earningsTrend", {}).get("trend", [])
        if t.get("period") in ("0q", "+1q", "0y", "+1y")
    ]

    earnings_hist = [
        EarningsHistoryEntry(
            quarter=_f(e, "quarter"),
            eps_estimate=_r(e, "epsEstimate"),
            eps_actual=_r(e, "epsActual"),
            eps_difference=_r(e, "epsDifference"),
            surprise_pct=_r(e, "surprisePercent"),
        )
        for e in analysis.get("earningsHistory", {}).get("history", [])
    ]

    rec_trend = [
        RecommendationSnapshot(
            period=t.get("period", ""),
            strong_buy=t.get("strongBuy", 0),
            buy=t.get("buy", 0),
            hold=t.get("hold", 0),
            sell=t.get("sell", 0),
            strong_sell=t.get("strongSell", 0),
        )
        for t in analysis.get("recommendationTrend", {}).get("trend", [])
    ]

    return YahooProfile(
        symbol=symbol,
        name=price_m.get("longName") or price_m.get("shortName"),
        exchange=price_m.get("exchangeName") or price_m.get("exchange"),
        currency=price_m.get("currency"),
        sector=profile_m.get("sector"),
        industry=profile_m.get("industry"),
        description=profile_m.get("longBusinessSummary"),
        employees=profile_m.get("fullTimeEmployees"),
        website=profile_m.get("website"),
        officers=officers,

        price=_r(price_m, "regularMarketPrice"),
        change_pct=_r(price_m, "regularMarketChangePercent"),
        market_cap=_r(price_m, "marketCap"),
        volume=int(_r(price_m, "regularMarketVolume") or 0) or None,
        avg_volume=int(_r(detail_m, "averageVolume") or 0) or None,
        week_52_high=_r(detail_m, "fiftyTwoWeekHigh"),
        week_52_low=_r(detail_m, "fiftyTwoWeekLow"),
        beta=_r(detail_m, "beta"),

        pe_ratio=_r(detail_m, "trailingPE"),
        forward_pe=_r(detail_m, "forwardPE"),
        peg_ratio=_r(stats_m, "pegRatio"),
        eps=_r(stats_m, "trailingEps"),
        dividend_yield_pct=_pct(detail_m, "dividendYield"),
        enterprise_value=_r(stats_m, "enterpriseValue"),
        ev_revenue=_r(stats_m, "enterpriseToRevenue"),
        ev_ebitda=_r(stats_m, "enterpriseToEbitda"),

        profit_margin_pct=_pct(fin_m, "profitMargins"),
        operating_margin_pct=_pct(fin_m, "operatingMargins"),
        return_on_equity_pct=_pct(fin_m, "returnOnEquity"),
        return_on_assets_pct=_pct(fin_m, "returnOnAssets"),
        gross_margin_pct=_pct(fin_m, "grossMargins"),

        revenue=_r(fin_m, "totalRevenue"),
        ebitda=_r(fin_m, "ebitda"),
        net_income=_r(fin_m, "netIncomeToCommon"),
        free_cash_flow=_r(fin_m, "freeCashflow"),
        total_cash=_r(fin_m, "totalCash"),
        total_debt=_r(fin_m, "totalDebt"),

        short_ratio=_r(stats_m, "shortRatio"),
        short_pct_of_float=_pct(stats_m, "shortPercentOfFloat"),
        insider_pct=_pct(stats_m, "heldPercentInsiders"),
        institution_pct=_pct(stats_m, "heldPercentInstitutions"),
        shares_outstanding=_r(stats_m, "sharesOutstanding"),

        income_annual=_income_list("incomeStatementHistory", "incomeStatementHistory"),
        income_quarterly=_income_list("incomeStatementHistoryQuarterly", "incomeStatementHistory"),
        balance_annual=_parse_dom_balance(bs_dom),
        balance_quarterly=[],
        cashflow_annual=_parse_dom_cashflow(cf_dom),
        cashflow_quarterly=[],

        earnings_estimates=trend_entries,
        earnings_history=earnings_hist,
        recommendation_trend=rec_trend,
        **px_feat,
    )
