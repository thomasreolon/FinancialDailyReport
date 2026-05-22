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


def heuristic_score(company: ScreenedCompany) -> float:
    """Legacy weighted score in ~[0, 1] (MarketBeat, growth, screeners, P/E)."""
    score = 0.0
    yahoo = company.yahoo
    mb = company.marketbeat

    if mb and mb.consensus:
        total = (mb.consensus.buy_count or 0) + (mb.consensus.hold_count or 0) + (mb.consensus.sell_count or 0)
        if total > 0:
            score += 0.30 * (mb.consensus.buy_count or 0) / total

    upside = _parse_upside(mb.consensus.upside_pct if mb and mb.consensus else None)
    if upside is not None and upside > 0:
        score += 0.25 * min(upside / 50.0, 1.0)

    if len(yahoo.income_annual) >= 2:
        latest = yahoo.income_annual[0].net_income
        prev = yahoo.income_annual[1].net_income
        if latest is not None and prev is not None and prev > 0 and latest > prev:
            score += 0.20

    score += 0.15 * min(len(company.sources) / 4.0, 1.0)

    pe = yahoo.pe_ratio
    if pe is not None and 0 < pe < 50:
        if pe < 15:
            score += 0.10
        elif pe < 25:
            score += 0.06
        else:
            score += 0.02

    return score


def combined_score(company: ScreenedCompany) -> float:
    """Normalized blend for the 3rd pick: NN + heuristic on comparable scales."""
    h = heuristic_score(company)
    nn = company.nn_score
    if nn is not None:
        return (nn + 0.3) / 1.2 + h / 2.0
    return h / 2.0


def _pick_best(pool: list[ScreenedCompany], key) -> ScreenedCompany | None:
    if not pool:
        return None
    return max(pool, key=key)


def select_top_companies(result: PipelineResult, n: int = 3) -> list[ScreenedCompany]:
    """Pick top-n with three distinct ranking strategies (when n >= 3).

    1st (left):  highest nn_score
    2nd (center): highest heuristic_score among remaining
    3rd (right): highest combined_score among remaining

    Falls back to heuristic ordering when NN scores are missing.
    """
    remaining = list(result.companies)
    picks: list[ScreenedCompany] = []

    if n >= 1:
        with_nn = [c for c in remaining if c.nn_score is not None]
        first = _pick_best(with_nn, lambda c: c.nn_score) if with_nn else _pick_best(remaining, heuristic_score)
        if first:
            remaining.remove(first)
            picks.append(first)

    if n >= 2 and len(picks) < n:
        second = _pick_best(remaining, heuristic_score)
        if second:
            remaining.remove(second)
            picks.append(second)

    if n >= 3 and len(picks) < n:
        third = _pick_best(remaining, combined_score)
        if third:
            remaining.remove(third)
            picks.append(third)

    while len(picks) < n and remaining:
        next_pick = _pick_best(remaining, heuristic_score)
        if next_pick is None:
            break
        remaining.remove(next_pick)
        picks.append(next_pick)

    return picks
