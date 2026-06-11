"""
News pipeline.

Collects market news and analysis from multiple sources, enriches with Gemini LLM:
  - fx_summary:     Gemini summary of the latest @fxevolutionvideo YouTube transcript
  - macro_summary:  Gemini summary of the latest @DefiantGatekeeper weekly macro video
                    (ex-investment banker; oil/10Y/FedWatch framework)
  - financial_news: FT World headlines (FTWorldResult)
  - stonex_news:    StoneX daily market analysis (StoneXResult)
  - tikr_news:      TIKR blog posts (TIKRBlogResult)
  - gemini_news:    Gemini + Google Search grounded brief on key recent/upcoming market events

Usage:
    from src.pipelines.news import run_pipeline
    result = run_pipeline()
"""

from __future__ import annotations

from pydantic import BaseModel

from src.api.gemini import generate_lite, generate_with_search
from src.scrapers.news.ft_world import FTWorldResult, scrape_ft_world
from src.scrapers.news.stonex import StoneXResult, scrape_stonex
from src.scrapers.news.tikr_blog import TIKRBlogResult, scrape_tikr_blog
from src.scrapers.news.yt_scraper import YTScraper

_FX_CHANNEL = "@fxevolutionvideo"
_MACRO_CHANNEL = "@DefiantGatekeeper"

_FX_SUMMARY_PROMPT = """You are a financial analyst assistant.
Below is the transcript of a recent market analysis video from FX Evolution.
Write a concise summary (200-300 words) covering:
- Key market themes and trends discussed
- Notable currencies, commodities, or indices mentioned
- Any trade setups or directional views expressed
- Important economic events or data mentioned

Transcript:
{transcript}
"""

_MACRO_SUMMARY_PROMPT = """You are a financial analyst assistant.
Below is the transcript of the latest weekly market review from an ex-investment
banker (credit PE/hedge fund background). His framework tracks a small set of
macro dials and the narrative they form.

Write a structured summary (200-300 words) that extracts, when present:
- Oil price level and direction, and what he infers from it
- 10Y Treasury yield level/direction and what triggered moves
- FedWatch rate hike/cut probabilities AND how they changed week-over-week
- Labor/inflation data readouts and how he maps them to the Fed path
- Key earnings or guidance (especially AI/semiconductor bellwethers) and his read
- His overall directional stance for the coming weeks and the risks he flags

Report numbers exactly as stated. If a topic is not discussed, omit it.

Transcript:
{transcript}
"""

_MARKET_EVENTS_PROMPT = """You are a financial research assistant with access to current web data.
Provide a concise briefing (250-350 words) on the most important recent and upcoming events
for global stock and financial markets. Include:
- Major macro events from the past 7 days (central bank decisions, inflation data, earnings, geopolitical)
- Key scheduled events in the next 7 days (Fed meetings, CPI/PPI releases, major earnings, auctions)
- Any notable market-moving news (sector rotation, liquidity events, notable analyst calls)

Today's date context: use your search tools to find current information.
Be specific with dates, figures, and company/index names where available.
"""


class NewsPipelineResult(BaseModel):
    fx_summary: str | None
    macro_summary: str | None = None
    financial_news: FTWorldResult | None
    stonex_news: StoneXResult | None
    tikr_news: TIKRBlogResult | None
    gemini_news: str | None


def run_pipeline(verbose: bool = True) -> NewsPipelineResult:
    fx_summary: str | None = None
    macro_summary: str | None = None
    financial_news: FTWorldResult | None = None
    stonex_news: StoneXResult | None = None
    tikr_news: TIKRBlogResult | None = None
    gemini_news: str | None = None

    # ── FX Evolution transcript → Gemini summary ──────────────────────────────
    if verbose:
        print("  fx_evolution transcript...", end=" ", flush=True)
    try:
        yt_result = YTScraper(hours=24, channel=_FX_CHANNEL).scrape()
        if yt_result:
            if verbose:
                print(f"ok ({len(yt_result.transcript)} chars)  gemini summary...", end=" ", flush=True)
            fx_summary = generate_lite(
                _FX_SUMMARY_PROMPT.format(transcript=yt_result.transcript)
            )
            if verbose:
                print("ok")
        else:
            if verbose:
                print("no video in last 24h")
    except Exception as e:
        if verbose:
            print(f"FAILED ({e})")

    # ── Defiant Gatekeeper weekly macro review ────────────────────────────────
    if verbose:
        print("  defiant_gatekeeper transcript...", end=" ", flush=True)
    try:
        # Weekly uploads: a video from the past 7 days stays relevant all week.
        yt_result = YTScraper(hours=7 * 24, channel=_MACRO_CHANNEL).scrape()
        if yt_result:
            if verbose:
                print(f"ok ({len(yt_result.transcript)} chars)  gemini summary...", end=" ", flush=True)
            macro_summary = generate_lite(
                _MACRO_SUMMARY_PROMPT.format(transcript=yt_result.transcript)
            )
            if verbose:
                print("ok")
        else:
            if verbose:
                print("no video in last 7d")
    except Exception as e:
        if verbose:
            print(f"FAILED ({e})")

    # ── FT World ──────────────────────────────────────────────────────────────
    if verbose:
        print("  ft_world...", end=" ", flush=True)
    try:
        financial_news = scrape_ft_world()
        if verbose:
            print(f"ok ({financial_news.count} articles)")
    except Exception as e:
        if verbose:
            print(f"FAILED ({e})")

    # ── StoneX ────────────────────────────────────────────────────────────────
    if verbose:
        print("  stonex...", end=" ", flush=True)
    try:
        stonex_news = scrape_stonex()
        if verbose:
            wc = stonex_news.article.word_count if stonex_news.article else 0
            print(f"ok ({wc} words)")
    except Exception as e:
        if verbose:
            print(f"FAILED ({e})")

    # ── TIKR blog ─────────────────────────────────────────────────────────────
    if verbose:
        print("  tikr_blog...", end=" ", flush=True)
    try:
        tikr_news = scrape_tikr_blog()
        if verbose:
            print(f"ok ({tikr_news.count} posts)")
    except Exception as e:
        if verbose:
            print(f"FAILED ({e})")

    # ── Gemini + web search: recent market events ─────────────────────────────
    if verbose:
        print("  gemini web search...", end=" ", flush=True)
    try:
        gemini_news = generate_with_search(_MARKET_EVENTS_PROMPT)
        if verbose:
            print(f"ok ({len(gemini_news)} chars)")
    except Exception as e:
        if verbose:
            print(f"FAILED ({e})")

    return NewsPipelineResult(
        fx_summary=fx_summary,
        macro_summary=macro_summary,
        financial_news=financial_news,
        stonex_news=stonex_news,
        tikr_news=tikr_news,
        gemini_news=gemini_news,
    )
