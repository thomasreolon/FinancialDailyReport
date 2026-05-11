from __future__ import annotations

from src.api.gemini import generate
from src.pipelines.screened_stocks import ScreenedCompany
from src.pipelines.build_report.models import ChartPoint, CompanyReport


_COMPANY_TEXT_PROMPT = """You are a financial analyst writing a brief stock report.

Company: {name} ({ticker})
Sector: {sector}
Industry: {industry}
Current Price: {price}
Market Cap: {market_cap}
P/E Ratio: {pe}
P/B Ratio: {pb}
Revenue (TTM): {revenue}
Net Income (TTM): {net_income}
Analyst Consensus: {analyst_consensus}
Analyst Avg Price Target: {price_target}
Description: {description}

Write a concise 3-4 sentence investment commentary covering:
- What the company does and its market position
- Key financial health signals (growth, profitability, valuation)
- Why it stands out today (screening signal, momentum, or fundamental quality)
- One risk to watch

Be specific and data-driven. No generic filler sentences.
"""


def _fmt(v: float | None) -> str:
    if v is None:
        return "N/A"
    if abs(v) >= 1e12:
        return f"${v / 1e12:.2f}T"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.2f}M"
    return f"{v:.2f}"


def _build_chart(yahoo) -> list[ChartPoint]:
    # Index balance sheets by period for debt/assets lookup
    bs_by_period: dict[str, object] = {bs.period: bs for bs in (yahoo.balance_annual or []) if bs.period}

    points = []
    for stmt in yahoo.income_annual or []:
        bs = bs_by_period.get(stmt.period)
        debt_ratio = None
        if bs and bs.total_debt is not None and bs.total_assets:
            try:
                debt_ratio = round(bs.total_debt / bs.total_assets, 4)
            except ZeroDivisionError:
                pass
        points.append(ChartPoint(
            period=stmt.period,
            net_revenue=stmt.total_revenue,
            ebitda=stmt.operating_income,
            earnings=stmt.net_income,
            debt_assets_ratio=debt_ratio,
        ))
    return points


def build_companies(companies: list[ScreenedCompany]) -> list[CompanyReport]:
    result = []
    for company in companies:
        yahoo = company.yahoo
        mb = company.marketbeat

        # P/B = market_cap / most recent annual total_equity
        pb = None
        if yahoo.market_cap and yahoo.balance_annual:
            eq = yahoo.balance_annual[0].total_equity
            if eq and eq != 0:
                pb = round(yahoo.market_cap / eq, 2)

        analyst_consensus = "N/A"
        price_target = "N/A"
        if mb and mb.consensus:
            analyst_consensus = mb.consensus.overall or "N/A"
            price_target = mb.consensus.avg_price_target or "N/A"

        prompt = _COMPANY_TEXT_PROMPT.format(
            name=yahoo.name or company.ticker,
            ticker=company.ticker,
            sector=yahoo.sector or "N/A",
            industry=yahoo.industry or "N/A",
            price=yahoo.price or "N/A",
            market_cap=_fmt(yahoo.market_cap),
            pe=yahoo.pe_ratio or "N/A",
            pb=pb or "N/A",
            revenue=_fmt(yahoo.revenue),
            net_income=_fmt(yahoo.net_income),
            analyst_consensus=analyst_consensus,
            price_target=price_target,
            description=(yahoo.description or "")[:500],
        )

        try:
            text = generate(prompt)
        except Exception as exc:
            text = f"[LLM generation failed: {exc}]"

        result.append(CompanyReport(
            ticker=company.ticker,
            name=yahoo.name,
            price=yahoo.price,
            price_now=yahoo.price,
            market_cap=yahoo.market_cap,
            pe=yahoo.pe_ratio,
            pb=pb,
            description=yahoo.description,
            text=text,
            chart=_build_chart(yahoo),
        ))
    return result
