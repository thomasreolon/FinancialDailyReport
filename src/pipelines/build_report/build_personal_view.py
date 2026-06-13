"""
Builds the optional "Personal View" section of the daily report.

Inputs blended into the Gemini prompt:
    - today's two main articles (news synthesis + macro view)
    - yesterday's first article (loaded from GCS — missing is fine)
    - the Global Asset Performance variations from today's run
    - the contents of personal_view.md at the repo root (user's own notes)

If the markdown file is missing/empty the section is skipped (returns None) so
the report still validates and the frontend simply hides the panel.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.api.gemini import generate
from src.pipelines.build_report.models import AssetVariation, PersonalView

_BUCKET = "the-mind-financial-reports"
_PREFIX = "raw"

# personal_view.md lives at the repo root. The pipeline job copies it into the
# container; see Dockerfile (`job` stage).
_PERSONAL_MD = Path(__file__).resolve().parents[3] / "personal_view.md"


_PROMPT = """Sei un investitore con decenni di esperienza, il cui stile di analisi si ispira a Ray Dalio e Warren Buffett: pragmatico, paziente, orientato al lungo periodo. Parli in modo diretto e semplice — come spiegheresti qualcosa a un amico intelligente che non lavora in finanza. Non usi gergo tecnico, non sei allarmista, non sei ideologico.

Curi una brevissima rubrica personale chiamata "Personal View".

Scrivi interamente in italiano. Mantieni i marcatori di formato TITLE: e ARTICLE: in inglese.

REGOLE DI SCRITTURA (rispettale sempre):
- Tono: calmo, concreto, mai sensazionalistico. Niente punti esclamativi, niente titoli da clickbait.
- Linguaggio: frasi brevi, parole semplici. Se usi un termine tecnico, spiegalo in due parole.
- Niente ideologia: non commentare la distribuzione della ricchezza, le classi sociali o la politica in termini di conflitto. Se un dato è rilevante, citalo come dato, non come prova di un sistema rotto.
- Niente teorie del complotto: non suggerire che i mercati siano manipolati, che le aziende mentano sistematicamente, o che i dati ufficiali siano falsi.
- Niente previsioni precise: non dare date esatte di crash o target di prezzo secchi. Parla di scenari e probabilità.
- Le note personali dell'autore sono idee di fondo da usare SOLO quando qualcosa di concreto nel flusso di notizie di oggi le rende rilevanti. Non forzarle: se oggi non c'è nulla che le colleghi, ignora quella nota e commenta cosa è effettivamente successo.

=== Note personali dell'autore (usa solo se rilevanti per le notizie di oggi) ===
{personal_notes}

=== Articolo principale di oggi ===
TITOLO: {today_title}
{today_article}

=== Vista macro di oggi ===
TITOLO: {today_title2}
{today_article2}

=== Articolo principale di ieri ===
TITOLO: {yesterday_title}
{yesterday_article}

=== Performance globale degli asset (oggi) ===
{variations}

Scrivi:
1. Un TITOLO breve (max 10 parole) che descriva semplicemente la cosa più importante di oggi.
2. Un ARTICOLO (100-150 parole) che:
   - Spieghi cosa è successo oggi e come si confronta con ieri, in modo che un lettore non esperto capisca
   - Se una nota dell'autore è naturalmente connessa agli eventi di oggi, integrarla senza forzature
   - Si chiuda con una cosa concreta da tenere d'occhio nei prossimi giorni

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
        title = lines[0] if lines else "Personal View"
        article_lines = lines[1:]
    return title.strip(), "\n".join(article_lines).strip()


def _read_personal_notes() -> str:
    try:
        text = _PERSONAL_MD.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    return text


def _load_yesterday() -> tuple[str, str] | None:
    """Return (title, article) of yesterday's first article, or None."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    blob_name = f"{_PREFIX}/{yesterday}.json"
    try:
        from google.cloud import storage  # type: ignore

        blob = storage.Client().bucket(_BUCKET).blob(blob_name)
        if not blob.exists():
            return None
        data = json.loads(blob.download_as_text())
    except Exception as exc:
        print(f"  [personal_view] yesterday fetch failed: {exc}")
        return None
    report = data.get("report") or {}
    title = report.get("title") or ""
    article = report.get("article") or ""
    if not article:
        return None
    return title, article


def _fmt_variations(variations: list[AssetVariation]) -> str:
    def _pct(v: float | None) -> str:
        return "—" if v is None else f"{v:+.2f}%"

    lines = []
    for v in variations:
        p = v.periods
        lines.append(
            f"- {v.name} ({v.symbol}): 1d {_pct(p.one_day)}, 5d {_pct(p.five_days)}, "
            f"1m {_pct(p.one_month)}, 1y {_pct(p.one_year)}, 3y {_pct(p.three_years)}"
        )
    return "\n".join(lines) if lines else "N/A"


def build_personal_view(
    today_title: str,
    today_article: str,
    today_title2: str,
    today_article2: str,
    variations: list[AssetVariation],
) -> PersonalView | None:
    """Returns a PersonalView, or None if the user's markdown file is empty/missing."""
    personal_notes = _read_personal_notes()
    if not personal_notes:
        return None

    yesterday = _load_yesterday()
    if yesterday is None:
        y_title, y_article = "N/A", "N/A"
    else:
        y_title, y_article = yesterday

    prompt = _PROMPT.format(
        personal_notes=personal_notes,
        today_title=today_title or "N/A",
        today_article=today_article or "N/A",
        today_title2=today_title2 or "N/A",
        today_article2=today_article2 or "N/A",
        yesterday_title=y_title or "N/A",
        yesterday_article=y_article or "N/A",
        variations=_fmt_variations(variations),
    )

    try:
        text = generate(prompt)
    except Exception as exc:
        # Never publish a raw error string into the UI — the central Gemini
        # router already retried transient failures, so fall back to clean text.
        print(f"  [build_personal_view] generation failed: {exc}")
        return PersonalView(
            title="Personal View",
            article="La nota personale non è disponibile per questa edizione.",
        )

    title, article = _parse_response(text)
    return PersonalView(title=title, article=article)
