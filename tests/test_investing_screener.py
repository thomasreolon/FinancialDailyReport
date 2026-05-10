"""
Integration test for src/scrapers/investing_screener.py.
"""
import json

import pytest

from src.scrapers.investing_screener import ScreenerResult, ScreenerRow, scrape_mid_cap_losers


class TestScreener:
    @pytest.fixture(scope="class")
    def result(self) -> ScreenerResult:
        return scrape_mid_cap_losers(limit=5)

    def test_returns_pydantic_model(self, result: ScreenerResult) -> None:
        assert isinstance(result, ScreenerResult)

    def test_has_rows(self, result: ScreenerResult) -> None:
        assert 1 <= len(result.rows) <= 5

    def test_row_fields_populated(self, result: ScreenerResult) -> None:
        row = result.rows[0]
        assert isinstance(row, ScreenerRow)
        assert row.ticker
        assert row.name
        assert row.day_change_pct is not None

    def test_sorted_worst_first(self, result: ScreenerResult) -> None:
        changes = [r.day_change_pct for r in result.rows if r.day_change_pct is not None]
        assert changes == sorted(changes), "rows should be sorted ascending by day_change_pct"

    def test_json_serializable(self, result: ScreenerResult) -> None:
        data = json.loads(result.model_dump_json())
        assert "rows" in data
        assert "total_in_universe" in data
        assert isinstance(data["rows"], list)
