"""Tests for tech-discoveries parsing and article2 indicator deltas."""

from __future__ import annotations

from src.pipelines.build_report.build_articles import _fmt_deltas
from src.pipelines.macro_indicators import MacroIndicatorsResult
from src.pipelines.tech_discoveries import _parse


def test_tech_parse_multiple_items():
    text = """ITEM
TITLE: Nuovo chip fotonico
SUMMARY: Azienda X presenta un chip fotonico
con throughput doppio.
IMPACT: Rilevante per i produttori di datacenter.

ITEM
TITLE: Batteria allo stato solido
SUMMARY: Y annuncia produzione pilota.
"""
    items = _parse(text)
    assert len(items) == 2
    assert items[0].title == "Nuovo chip fotonico"
    # continuation line is folded into the summary
    assert "throughput doppio" in items[0].summary
    assert items[0].impact == "Rilevante per i produttori di datacenter."
    assert items[1].impact is None


def test_tech_parse_incomplete_item_dropped():
    items = _parse("ITEM\nTITLE: Solo titolo, niente summary\n")
    assert items == []


def test_fmt_deltas_with_previous_run():
    macro = MacroIndicatorsResult(vix=20.0, breakeven_10y=2.4)
    prev = [("2026-06-10", {"vix": 17.5, "breakeven_10y": 2.4})]
    out = _fmt_deltas(macro, prev)
    assert "VIX" in out
    assert "+2.5" in out
    assert "2026-06-10" in out


def test_fmt_deltas_no_archive():
    out = _fmt_deltas(MacroIndicatorsResult(vix=20.0), [])
    assert out.startswith("N/A")


def test_gcs_normalise_old_report():
    from report_server.gcs import _normalise

    old_report = {
        "report": {
            "title": "Old Report Title",
            "article": "Body of the old report.",
            "title2": "Macro View",
            "article2": "Body of macro view.",
            "generated_at": "2026-06-01T09:00:00",
            "variations": [
                {
                    "symbol": "SPY",
                    "name": "S&P 500 ETF",
                    "periods": {
                        "one_day": 0.015,
                        "five_days": 0.02,
                        "one_month": 0.05,
                        "one_year": 0.15,
                        "three_years": 0.35,
                    }
                }
            ]
        }
    }

    normalised = _normalise(old_report)
    
    # Check that normalisation succeeded and populated defaults
    assert "report" in normalised
    rep = normalised["report"]
    assert rep["title"] == "Old Report Title"
    
    variations = rep["variations"]
    assert len(variations) == 1
    v = variations[0]
    assert v["symbol"] == "SPY"
    # These fields were not in old_report, but should be filled with defaults
    assert v["invert_color"] is False
    assert v["now_value"] is None
    assert v["now_suffix"] == ""

