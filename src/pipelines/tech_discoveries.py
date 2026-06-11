"""
Tech discoveries pipeline.

Single Gemini call with Google Search grounding that surfaces the week's most
investor-relevant technology/science breakthroughs (AI, semiconductors, energy,
biotech, space, robotics). Output is parsed from marker-format text rather than
a second structured-extraction call to keep the per-run Gemini cost at one call.

Usage:
    from src.pipelines.tech_discoveries import run_pipeline
    result = run_pipeline()
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from src.api.gemini import generate_with_search
from src.pipelines.build_report.models import TechDiscovery

_PROMPT = """Sei un analista tecnologico che scrive per un report finanziario giornaliero.
Oggi è {today}.

Cerca sul web le 3-4 scoperte o svolte tecnologiche/scientifiche più rilevanti degli
ultimi 7 giorni (rispetto a oggi, {today}) per un investitore: AI e modelli,
semiconduttori, energia (batterie, nucleare, fusione, solare), biotech/farmaceutica,
spazio, robotica, quantum computing. Scarta qualsiasi notizia più vecchia di 14 giorni.

Criteri: novità concrete (annunci, paper, demo, approvazioni regolatorie, contratti),
non rumor né opinioni. Preferisci notizie con un impatto plausibile su aziende quotate
o settori interi.

Scrivi in italiano. Per OGNI scoperta usa ESATTAMENTE questo formato (marcatori in inglese):

ITEM
TITLE: <titolo conciso, max 12 parole>
SUMMARY: <2-3 frasi: cosa è successo, chi, con quali numeri/fatti>
IMPACT: <1-2 frasi: perché conta per i mercati — settori o aziende quotate toccate>

Non aggiungere testo prima del primo ITEM né dopo l'ultimo IMPACT.
"""


class TechDiscoveriesResult(BaseModel):
    discoveries: list[TechDiscovery] = Field(default_factory=list)
    raw_text: str | None = None
    fetched_at: str = ""


def _parse(text: str) -> list[TechDiscovery]:
    discoveries: list[TechDiscovery] = []
    current: dict[str, str] = {}

    def _flush() -> None:
        if current.get("title") and current.get("summary"):
            discoveries.append(TechDiscovery(
                title=current["title"],
                summary=current["summary"],
                impact=current.get("impact"),
            ))
        current.clear()

    field = None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "ITEM" or stripped.startswith("ITEM"):
            _flush()
            field = None
        elif stripped.startswith("TITLE:"):
            current["title"] = stripped.removeprefix("TITLE:").strip()
            field = None
        elif stripped.startswith("SUMMARY:"):
            current["summary"] = stripped.removeprefix("SUMMARY:").strip()
            field = "summary"
        elif stripped.startswith("IMPACT:"):
            current["impact"] = stripped.removeprefix("IMPACT:").strip()
            field = "impact"
        elif stripped and field:
            current[field] = f"{current[field]} {stripped}"
    _flush()
    return discoveries


def run_pipeline(verbose: bool = True) -> TechDiscoveriesResult:
    result = TechDiscoveriesResult(fetched_at=datetime.now(timezone.utc).isoformat())
    if verbose:
        print("  tech discoveries (gemini web search)...", end=" ", flush=True)
    try:
        raw = generate_with_search(
            _PROMPT.format(today=datetime.now(timezone.utc).date().isoformat())
        )
    except Exception as exc:
        if verbose:
            print(f"FAILED ({exc})")
        return result
    result.raw_text = raw
    result.discoveries = _parse(raw)
    if verbose:
        print(f"ok ({len(result.discoveries)} items)")
    return result
