from __future__ import annotations

from src.api.gemini import generate
from src.pipelines.build_report.models import CompanyReport, IndicatorReport
from src.pipelines.macro_indicators import MacroIndicatorsResult
from src.pipelines.news import NewsPipelineResult


_ARTICLE1_PROMPT = """You are a senior financial journalist writing a daily market briefing.

Synthesize the news sources below into a compelling market briefing for today.

=== FT World Headlines ===
{ft_headlines}

=== StoneX Daily Analysis ===
{stonex_article}

=== TIKR Blog Posts ===
{tikr_posts}

=== General Market Events (web search) ===
{gemini_news}

=== FX/Macro Video Summary ===
{fx_summary}

Write:
1. A punchy, specific TITLE (max 10 words) capturing the most important market theme.
2. An ARTICLE (200-300 words) that:
   - Opens with the most market-moving event or theme
   - Covers 2-3 key developments across equities, rates, and macro
   - Includes specific data points, index levels, or percentage moves where available
   - Closes with what to watch next

Format:
TITLE: <title>
ARTICLE: <article>
"""

_ARTICLE2_PROMPT = """You are a macro strategist writing the 'big picture' section of a daily market report.

=== Current Macro Indicators ===
{indicators_summary}

=== Today's Top Selected Stocks ===
{companies_summary}

Write:
1. A TITLE (max 10 words) summarizing the current macro regime.
2. An ARTICLE (250-350 words) that:
   - Opens with a bird's-eye view of where markets stand in the economic cycle
   - Describes the 2-3 dominant macro forces currently driving markets
   - Gives 2-3 specific causal warnings using the format:
     "If [event] happens [timeframe], it would be [bullish/bearish] because [mechanism]."
   - Notes any cross-asset divergences or signals worth monitoring
   - Is grounded entirely in the indicator data provided above

Format:
TITLE: <title>
ARTICLE: <article>
"""


def _parse_response(text: str) -> tuple[str, str]:
    title = ""
    article_lines: list[str] = []
    in_article = False
    for line in text.split("\n"):
        if line.startswith("TITLE:"):
            title = line.removeprefix("TITLE:").strip()
        elif line.startswith("ARTICLE:"):
            in_article = True
            rest = line.removeprefix("ARTICLE:").strip()
            if rest:
                article_lines.append(rest)
        elif in_article:
            article_lines.append(line)
    if not title:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        title = lines[0] if lines else "Daily Market Briefing"
        article_lines = lines[1:]
    return title.strip(), "\n".join(article_lines).strip()


def build_title_article(news: NewsPipelineResult) -> tuple[str, str]:
    ft_headlines = "N/A"
    if news.financial_news and news.financial_news.articles:
        ft_headlines = "\n".join(
            f"- {a.title}: {a.teaser or ''}"
            for a in news.financial_news.articles[:10]
        )

    stonex_article = "N/A"
    if news.stonex_news and news.stonex_news.article:
        art = news.stonex_news.article
        stonex_article = "\n".join(art.paragraphs)[:2000]

    tikr_posts = "N/A"
    if news.tikr_news and news.tikr_news.posts:
        tikr_posts = "\n".join(
            f"- {p.title}: {p.excerpt or ''}" for p in news.tikr_news.posts[:5]
        )

    prompt = _ARTICLE1_PROMPT.format(
        ft_headlines=ft_headlines,
        stonex_article=stonex_article,
        tikr_posts=tikr_posts,
        gemini_news=news.gemini_news or "N/A",
        fx_summary=news.fx_summary or "N/A",
    )

    try:
        text = generate(prompt)
    except Exception as exc:
        return "Daily Market Briefing", f"[LLM generation failed: {exc}]"

    return _parse_response(text)


def build_title2_article2(
    indicators: list[IndicatorReport],
    companies: list[CompanyReport],
    macro: MacroIndicatorsResult,
) -> tuple[str, str]:
    indicators_summary = "\n".join(
        f"- {i.name}: {i.value} [{i.color.upper()}]" for i in indicators
    )
    companies_summary = "\n".join(
        f"- {c.ticker} ({c.name}): price ${c.price}, P/E {c.pe}, market cap {c.market_cap}"
        for c in companies
    )

    prompt = _ARTICLE2_PROMPT.format(
        indicators_summary=indicators_summary,
        companies_summary=companies_summary,
    )

    try:
        text = generate(prompt)
    except Exception as exc:
        return "Macro Outlook", f"[LLM generation failed: {exc}]"

    return _parse_response(text)
