from __future__ import annotations

from src.api.gemini import generate
from src.pipelines.build_report.models import CompanyReport, IndicatorReport
from src.pipelines.macro_indicators import MacroIndicatorsResult
from src.pipelines.news import NewsPipelineResult


_ARTICLE1_PROMPT = """Sei un giornalista finanziario senior che scrive il briefing di mercato giornaliero.

Sintetizza le fonti di notizie seguenti in un briefing di mercato avvincente per oggi.
Scrivi interamente in italiano. Mantieni i marcatori di formato TITLE: e ARTICLE: in inglese.

=== Titoli FT World ===
{ft_headlines}

=== Analisi Giornaliera StoneX ===
{stonex_article}

=== Post del Blog TIKR ===
{tikr_posts}

=== Eventi di Mercato Generali (ricerca web) ===
{gemini_news}

=== Sintesi Video FX/Macro ===
{fx_summary}

Scrivi:
1. Un TITOLO incisivo e specifico (max 10 parole) che cattura il tema di mercato più importante.
2. Un ARTICOLO (200-300 parole) che:
   - Apre con l'evento o tema più rilevante per i mercati
   - Copre 2-3 sviluppi chiave tra azionario, tassi e macro
   - Include dati specifici, livelli degli indici o movimenti percentuali dove disponibili
   - Chiude con cosa osservare nelle prossime ore

Formato:
TITLE: <titolo>
ARTICLE: <articolo>
"""

_ARTICLE2_PROMPT = """Sei un macro strategist che scrive la sezione 'quadro generale' di un report di mercato giornaliero.

Scrivi interamente in italiano. Mantieni i marcatori di formato TITLE: e ARTICLE: in inglese.

=== Indicatori Macro Attuali ===
{indicators_summary}

=== Titoli Azionari Selezionati Oggi ===
{companies_summary}

Scrivi:
1. Un TITOLO (max 10 parole) che riassume il regime macro attuale.
2. Un ARTICOLO (250-350 parole) che:
   - Apre con una visione d'insieme di dove si trovano i mercati nel ciclo economico
   - Descrive le 2-3 forze macro dominanti che guidano attualmente i mercati
   - Fornisce 2-3 avvertimenti causali specifici usando il formato:
     "Se [evento] accade [arco temporale], sarebbe [rialzista/ribassista] perché [meccanismo]."
   - Segnala eventuali divergenze o segnali cross-asset da monitorare
   - È fondato esclusivamente sui dati degli indicatori forniti sopra

Formato:
TITLE: <titolo>
ARTICLE: <articolo>
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
        title = lines[0] if lines else "Aggiornamento Mercati"
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
        return "Aggiornamento Mercati", f"[Generazione LLM fallita: {exc}]"

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
        return "Prospettiva Macro", f"[Generazione LLM fallita: {exc}]"

    return _parse_response(text)
