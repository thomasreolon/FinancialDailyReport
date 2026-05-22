from __future__ import annotations

import re

from src.pipelines.screened_stocks import PipelineResult, ScreenedCompany


def _parse_upside(s: str | None) -> float | None:
    if not s:
        return None
    v = re.sub(r"[^0-9.\-]", "", s)
    try:
        return float(v)
    except ValueError:
        return None


def _score(company: ScreenedCompany) -> float:
    score = 0.0
    yahoo = company.yahoo
    mb = company.marketbeat

    # Analyst buy consensus from MarketBeat (0.30)
    if mb and mb.consensus:
        total = (mb.consensus.buy_count or 0) + (mb.consensus.hold_count or 0) + (mb.consensus.sell_count or 0)
        if total > 0:
            score += 0.30 * (mb.consensus.buy_count or 0) / total

    # Analyst upside (0.25) — cap at 50% upside = full score
    upside = _parse_upside(mb.consensus.upside_pct if mb and mb.consensus else None)
    if upside is not None and upside > 0:
        score += 0.25 * min(upside / 50.0, 1.0)

    # Net income growing YoY (0.20)
    if len(yahoo.income_annual) >= 2:
        latest = yahoo.income_annual[0].net_income
        prev = yahoo.income_annual[1].net_income
        if latest is not None and prev is not None and prev > 0 and latest > prev:
            score += 0.20

    # Screener count — more screeners = stronger signal (0.15)
    score += 0.15 * min(len(company.sources) / 4.0, 1.0)

    # P/E ratio: lower is better (0.10)
    pe = yahoo.pe_ratio
    if pe is not None and 0 < pe < 50:
        if pe < 15:
            score += 0.10
        elif pe < 25:
            score += 0.06
        else:
            score += 0.02

    return score


def select_top_companies(result: PipelineResult, n: int = 3) -> list[ScreenedCompany]:
    """Pick the top-n screened companies.

    Prefers the NN composite score (set by the build_report pipeline). Falls
    back to the legacy heuristic _score for any company without an NN score so
    the report still produces n picks even on a cold day.
    """
    with_nn:    list[ScreenedCompany] = [c for c in result.companies if c.nn_score is not None]
    without_nn: list[ScreenedCompany] = [c for c in result.companies if c.nn_score is None]

    with_nn.sort(key=lambda c: c.nn_score, reverse=True)
    without_nn.sort(key=_score, reverse=True)

    picks: list[ScreenedCompany] = with_nn[:n]
    if len(picks) < n:
        picks.extend(without_nn[: n - len(picks)])
    return picks
