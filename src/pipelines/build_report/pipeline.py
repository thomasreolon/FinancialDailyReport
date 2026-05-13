"""
build_report pipeline.

Runs all upstream pipelines (news, macro_indicators, screened_stocks) and the
market overview scraper, then assembles a structured DailyReport Pydantic model.

Checkpoint behaviour: each upstream stage is pickled to
/tmp/ee_mind_report_<date>/ after completion.  On a crash and re-run the
completed stages are reloaded from disk, so only failed/remaining stages
actually execute.  Pass force=True to ignore checkpoints and re-run everything.

Usage:
    from src.pipelines.build_report import run_pipeline
    report = run_pipeline()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.pipelines.build_report import _checkpoints as ckpt
from src.pipelines.build_report.build_articles import build_title_article, build_title2_article2
from src.pipelines.build_report.build_companies import build_companies
from src.pipelines.build_report.build_indicators import build_indicators
from src.pipelines.build_report.build_variations import build_variations
from src.pipelines.build_report.models import DailyReport
from src.pipelines.build_report.select_companies import select_top_companies


@dataclass
class PipelineBundle:
    report: DailyReport
    news: object        # NewsPipelineResult
    macro: object       # MacroIndicatorsResult
    screened: object    # PipelineResult (screened_stocks)
    overview: object    # MarketOverviewResult


def _cached(name: str, fn, force: bool, verbose: bool) -> object:
    if not force and ckpt.exists(name):
        if verbose:
            print(f"  [{name}] loaded from checkpoint (/tmp/ee_mind_report_*/{ name }.pkl)")
        return ckpt.load(name)
    result = fn()
    ckpt.save(name, result)
    return result


def run_pipeline(verbose: bool = True, force: bool = False) -> PipelineBundle:
    """
    Args:
        verbose: print progress to stdout.
        force:   ignore today's checkpoints and re-run all upstream stages.
    """
    def _log(msg: str) -> None:
        if verbose:
            print(f"  {msg}")

    # ── upstream pipelines (checkpointed) ─────────────────────────────────────
    _log("Running news pipeline...")
    from src.pipelines.news import run_pipeline as _run_news
    news = _cached("news", lambda: _run_news(verbose=verbose), force, verbose)

    _log("Running macro_indicators pipeline...")
    from src.pipelines.macro_indicators import run_pipeline as _run_macro
    macro = _cached("macro_indicators", _run_macro, force, verbose)

    _log("Running screened_stocks pipeline...")
    from src.pipelines.screened_stocks import run_pipeline as _run_screened
    screened = _cached("screened_stocks", lambda: _run_screened(verbose=verbose), force, verbose)

    _log("Fetching market overview (variations)...")
    from src.scrapers.technical.market_overview import MarketOverviewResult, scrape_market_overview
    try:
        overview = _cached("market_overview", scrape_market_overview, force, verbose)
    except Exception as exc:
        _log(f"market_overview failed ({exc}) — variations will be empty")
        overview = MarketOverviewResult(groups=[])

    # ── select top 3 companies ─────────────────────────────────────────────────
    top3 = select_top_companies(screened, n=3)
    if verbose:
        print(f"  Top 3 selected: {[c.ticker for c in top3]}")

    # ── build sections ─────────────────────────────────────────────────────────
    _log("Building indicators section...")
    indicators = build_indicators(macro)

    _log("Building companies section (LLM commentary per company)...")
    companies = build_companies(top3)

    _log("Building variations section...")
    variations = build_variations(overview)

    # ── LLM articles ───────────────────────────────────────────────────────────
    _log("Building article 1 (news synthesis)...")
    title, article = build_title_article(news)

    _log("Building article 2 (macro view)...")
    title2, article2 = build_title2_article2(indicators, companies, macro)

    report = DailyReport(
        title=title,
        article=article,
        companies=companies,
        indicators=indicators,
        title2=title2,
        article2=article2,
        variations=variations,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    return PipelineBundle(
        report=report,
        news=news,
        macro=macro,
        screened=screened,
        overview=overview,
    )
