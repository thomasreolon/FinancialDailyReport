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


_PROMPT = """Sei un analista di mercato che cura una brevissima rubrica personale chiamata "Personal View".

Scrivi interamente in italiano. Mantieni i marcatori di formato TITLE: e ARTICLE: in inglese.
La rubrica deve riflettere il punto di vista personale dell'autore (vedi sotto), confrontandolo con il flusso di notizie di oggi e di ieri e con i movimenti degli asset globali. Sii diretto, opinionato e conciso: questa non è una sintesi neutra.
L'articolo deve essere calmo e raccontato in modo chiaro, conciso e professionale.

=== Note personali dell'autore (priorità massima — usa queste come tesi) ===
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
1. Un TITOLO breve (max 10 parole) che catturi la tesi personale del giorno.
2. Un ARTICOLO (100-150 parole) che:
   - Confronti il quadro di oggi con quello di ieri evidenziando cosa è cambiato
   - Si chiuda con un'azione o un'osservazione concreta da monitorare legata alla tesi personale o a importanti avvenimenti che potrebbero influenzare il comportamento del mercato

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
        return PersonalView(
            title="Personal View",
            article=f"[Generazione LLM fallita: {exc}]",
        )

    title, article = _parse_response(text)
    return PersonalView(title=title, article=article)
