from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.api.gemini import generate
from src.pipelines.build_report.models import CompanyReport, IndicatorReport
from src.pipelines.macro_indicators import MacroIndicatorsResult
from src.pipelines.news import NewsPipelineResult

_BUCKET = "the-mind-financial-reports"
_PREFIX = "raw"


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

REGOLE DI ANALISI (catene di trasmissione macro — applicale ai dati qui sotto):
- Petrolio e rendimento 10Y sono i due quadranti principali. Petrolio in rialzo → pressione
  inflazionistica → Fed restrittiva più a lungo → rendimenti su → multipli azionari compressi
  (ribassista). Petrolio in calo → disinflazione → spazio per tagli (rialzista).
- Un movimento rapido del 10Y (≈15-20bp in pochi giorni) comprime le valutazioni growth
  anche senza notizie sugli utili. Usa i delta, non solo il livello.
- Probabilità FedWatch: conta la VARIAZIONE rispetto ai giorni precedenti più del livello.
  Un passaggio da "taglio probabile" a "rialzo probabile" è uno shock di regime.
- Catena lavoro → inflazione → Fed: dati sul lavoro caldi (quits/JOLTS, salari) → pressione
  salariale → inflazione persistente → Fed restrittiva → ribassista per growth e bond lunghi.
- Guidance dei bellwether AI/semiconduttori: una guidance debole pesa su tutto il tech e
  sugli indici, dato il loro peso; va citata se presente nelle fonti.
- Credito anticipa l'azionario: allargamento degli spread IG/CCC = risk-off in costruzione.
- Rame/oro in calo + curva invertita = segnale di rallentamento della crescita.

=== Indicatori Macro Attuali ===
{indicators_summary}

=== Variazioni Indicatori vs Giorni Precedenti ===
{deltas_summary}

=== Sintesi Video Macro Settimanale (ex-investment banker) ===
{macro_summary}

=== Titoli Azionari Selezionati Oggi ===
{companies_summary}

Scrivi:
1. Un TITOLO (max 10 parole) che riassume il regime macro attuale.
2. Un ARTICOLO (250-350 parole) che:
   - Apre con una visione d'insieme di dove si trovano i mercati nel ciclo economico
   - Identifica cosa sta CAMBIANDO usando le variazioni vs giorni precedenti, non solo i livelli
   - Descrive le 2-3 forze macro dominanti applicando le catene di trasmissione sopra
   - Fornisce 2-3 avvertimenti causali specifici usando il formato:
     "Se [evento] accade [arco temporale], sarebbe [rialzista/ribassista] perché [meccanismo]."
   - Segnala eventuali divergenze o segnali cross-asset da monitorare
   - È fondato esclusivamente sui dati forniti sopra

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
        print(f"  [build_articles] article1 generation failed: {exc}")
        return "Aggiornamento Mercati", _fallback_article1(news)

    return _parse_response(text)


def _fallback_article1(news: NewsPipelineResult) -> str:
    """Readable fallback when the LLM is unavailable — never publish a raw error."""
    lines = [
        "La sintesi automatica non è disponibile per questa edizione. "
        "Di seguito i titoli principali raccolti oggi:",
        "",
    ]
    if news.financial_news and news.financial_news.articles:
        lines += [f"• {a.title}" for a in news.financial_news.articles[:8]]
    else:
        lines.append("• Nessuna notizia disponibile dalle fonti odierne.")
    return "\n".join(lines)


# ── indicator deltas vs previous archived runs ───────────────────────────────

# MacroIndicatorsResult fields that move on a daily/weekly basis and feed the
# transmission chains in the article2 prompt. Monthly series (PCE, PMI, LEI...)
# are excluded: their day-over-day delta is almost always zero or a data lag.
_DELTA_FIELDS: list[tuple[str, str]] = [
    ("vix", "VIX"),
    ("fear_greed", "Fear & Greed"),
    ("yield_curve_10y3m", "Curva 10A-3M (pp)"),
    ("real_yield_10y", "Rendimento reale 10A (%)"),
    ("breakeven_10y", "Breakeven 10A (%)"),
    ("fed_cut_probability_pct", "Prob. taglio Fed (%)"),
    ("ig_spread", "Spread IG (pp)"),
    ("ccc_spread", "Spread CCC (pp)"),
    ("move_index", "Indice MOVE"),
    ("copper_gold_ratio", "Rame/Oro"),
    ("wti_contango_pct", "Contango WTI (%)"),
    ("sp500_fwd_pe", "P/E forward S&P 500"),
    ("rrp_facility_bln", "RRP ($B)"),
    ("tga_bln", "TGA ($B)"),
    ("aaii_bull_bear_spread", "AAII bull-bear (pp)"),
]


def _load_archived_indicators(days_back: int, client) -> tuple[str, dict] | None:
    """Return (date_str, macro_indicators dict) from the archive `days_back` days
    ago, scanning up to 2 extra days earlier to skip weekends/missed runs."""
    bucket = client.bucket(_BUCKET)
    for offset in range(days_back, days_back + 3):
        date_str = (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%d")
        blob = bucket.blob(f"{_PREFIX}/{date_str}.json")
        try:
            if not blob.exists():
                continue
            data = json.loads(blob.download_as_text())
        except Exception:
            continue
        macro = data.get("macro_indicators")
        if macro:
            return date_str, macro
    return None


def _load_previous_runs() -> list[tuple[str, dict]]:
    """Most recent prior archive plus one ~a week older, for day and week deltas."""
    try:
        from google.cloud import storage  # type: ignore

        client = storage.Client()
    except Exception as exc:
        print(f"  [build_articles] GCS unavailable, no indicator deltas: {exc}")
        return []
    runs = []
    prev = _load_archived_indicators(1, client)
    if prev:
        runs.append(prev)
    week = _load_archived_indicators(7, client)
    if week and (not prev or week[0] != prev[0]):
        runs.append(week)
    return runs


def _fmt_deltas(macro: MacroIndicatorsResult, previous: list[tuple[str, dict]]) -> str:
    if not previous:
        return "N/A (nessun archivio precedente disponibile)"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = []
    for field, label in _DELTA_FIELDS:
        now = getattr(macro, field, None)
        if now is None:
            continue
        parts = []
        for date_str, archived in previous:
            old = archived.get(field)
            if isinstance(old, (int, float)):
                parts.append(f"{date_str}: {old:g} (Δ {now - old:+g})")
        if parts:
            lines.append(f"- {label}: oggi ({today}) {now:g} | " + "; ".join(parts))
    return "\n".join(lines) if lines else "N/A (nessun campo confrontabile)"


def _fallback_article2(indicators: list[IndicatorReport]) -> str:
    """Readable fallback built from indicator colors — never publish a raw error."""
    red = [i.name for i in indicators if i.color == "red"]
    green = [i.name for i in indicators if i.color == "green"]
    lines = [
        "L'analisi macro automatica non è disponibile per questa edizione. "
        "Sintesi dal cruscotto indicatori:",
        "",
    ]
    if green:
        lines.append(f"Segnali favorevoli ({len(green)}): {', '.join(green)}.")
    if red:
        lines.append(f"Segnali di cautela ({len(red)}): {', '.join(red)}.")
    if not green and not red:
        lines.append("Nessun indicatore in zona estrema: quadro complessivamente neutrale.")
    return "\n".join(lines)


def build_title2_article2(
    indicators: list[IndicatorReport],
    companies: list[CompanyReport],
    macro: MacroIndicatorsResult,
    news: NewsPipelineResult | None = None,
) -> tuple[str, str]:
    def _fmt(i: IndicatorReport) -> str:
        if i.value is None:
            return i.label or "N/A"
        parts = [f"{i.value:g}"]
        if i.unit in ("pct", "pct+"):
            parts = [f"{i.value:+.2f}%" if "+" in i.unit else f"{i.value:.2f}%"]
        elif i.unit == "T$":
            parts = [f"${i.value:.2f}T"]
        elif i.unit == "B$":
            parts = [f"${i.value:.0f}B"]
        elif i.unit == "x":
            parts = [f"{i.value:.1f}x"]
        if i.label:
            parts.append(f"({i.label})")
        return " ".join(parts)

    indicators_summary = "\n".join(
        f"- {i.name}: {_fmt(i)} [{i.color.upper()}]" for i in indicators
    )
    companies_summary = "\n".join(
        f"- {c.ticker} ({c.name}): price ${c.price}, P/E {c.pe}, market cap {c.market_cap}"
        for c in companies
    )
    deltas_summary = _fmt_deltas(macro, _load_previous_runs())
    macro_summary = (news.macro_summary if news else None) or "N/A"

    prompt = _ARTICLE2_PROMPT.format(
        indicators_summary=indicators_summary,
        deltas_summary=deltas_summary,
        macro_summary=macro_summary,
        companies_summary=companies_summary,
    )

    try:
        text = generate(prompt)
    except Exception as exc:
        print(f"  [build_articles] article2 generation failed: {exc}")
        return "Prospettiva Macro", _fallback_article2(indicators)

    return _parse_response(text)
