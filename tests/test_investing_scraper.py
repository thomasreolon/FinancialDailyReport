"""
Integration tests for src/scrapers/stock/investing.py.

Test 1 — breadth : scrape 5 different companies (different exchanges, currencies,
         sectors) and verify the core fields parse without errors.
Test 2 — rate stress : scrape the same URL 15 times as fast as possible and
         check that none of the requests are blocked or rate-limited.
"""

import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import pytest

from src.scrapers.stock.investing import StockPage, scrape_investing_stock

# ── test targets ─────────────────────────────────────────────────────────────

COMPANIES = [
    {
        "name": "Samsung Electronics (KRW, Seoul)",
        "url": "https://www.investing.com/equities/samsung-electronics-co-ltd",
        "expected_currency": "KRW",
        "expected_symbol": "005930",
    },
    {
        "name": "Apple (USD, NASDAQ)",
        "url": "https://www.investing.com/equities/apple-computer-inc",
        "expected_currency": "USD",
        "expected_symbol": "AAPL",
    },
    {
        "name": "ASML (EUR, Amsterdam)",
        "url": "https://www.investing.com/equities/asml-holding",
        "expected_currency": "EUR",
        "expected_symbol": "ASML",
    },
    {
        "name": "Toyota (USD/JPY, NYSE ADR)",
        "url": "https://www.investing.com/equities/toyota",
        "expected_currency": None,   # USD on NYSE ADR
        "expected_symbol": "TM",
    },
    {
        "name": "HSBC (GBP, London)",
        "url": "https://www.investing.com/equities/hsbc-holdings",
        "expected_currency": None,   # GBp on LSE
        "expected_symbol": "HSBA",
    },
]

RATE_STRESS_URL = "https://www.investing.com/equities/apple-computer-inc"
RATE_STRESS_N   = 15


# ── helpers ───────────────────────────────────────────────────────────────────

@dataclass
class ScrapeResult:
    name: str
    url: str
    page: StockPage | None = None
    error: str | None = None
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.page is not None and self.error is None


def _scrape(name: str, url: str, timeout: int = 60) -> ScrapeResult:
    t0 = time.perf_counter()
    try:
        page = scrape_investing_stock(url, timeout=timeout)
        return ScrapeResult(name=name, url=url, page=page, duration_s=time.perf_counter() - t0)
    except Exception as exc:
        return ScrapeResult(
            name=name,
            url=url,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            duration_s=time.perf_counter() - t0,
        )


def _assert_page_valid(result: ScrapeResult, expected_currency: str | None, expected_symbol: str | None) -> None:
    assert result.ok, (
        f"\n[FAIL] {result.name}\n"
        f"  URL: {result.url}\n"
        f"  Duration: {result.duration_s:.1f}s\n"
        f"  Error: {result.error}"
    )

    page = result.page

    # identity
    assert page.name, "name is empty"
    assert page.symbol, "symbol is empty"
    assert page.currency, "currency is empty"

    if expected_currency:
        assert page.currency == expected_currency, (
            f"expected currency {expected_currency!r}, got {page.currency!r}"
        )
    if expected_symbol:
        assert page.symbol == expected_symbol, (
            f"expected symbol {expected_symbol!r}, got {page.symbol!r}"
        )

    # price
    assert page.price.current > 0, "current price must be positive"
    assert page.price.currency, "price.currency is empty"

    # key stats — at least some must be populated
    ks = page.key_stats
    populated = sum(
        v is not None
        for v in [
            ks.market_cap_raw, ks.revenue_raw, ks.eps,
            ks.pe_ratio, ks.price_to_book, ks.ebitda_raw,
            ks.return_on_equity_pct, ks.rsi_14, ks.isin,
        ]
    )
    assert populated >= 3, f"too few key stats populated ({populated}/9): {ks}"

    # technical
    assert page.technical.timeframe_signals, "no timeframe signals"
    assert page.technical.overall_signal, "no overall technical signal"

    # should have at least some news
    assert len(page.news) >= 1, "no news articles scraped"

    # analyst forecast (most stocks have one, but tolerate absence)
    if page.analyst_forecast:
        af = page.analyst_forecast
        assert af.consensus, "analyst consensus is empty"
        assert af.avg_price_target > 0, "avg price target is 0"
        assert af.total_analysts > 0, "total_analysts is 0"

    # dividends — just validate structure if present
    for div in page.dividends:
        assert div.amount > 0, f"dividend amount must be positive: {div}"

    # peer benchmarks
    assert len(page.peer_benchmarks) >= 3, "fewer than 3 peer benchmarks"

    # profile
    assert page.profile.sector or page.profile.industry or page.profile.description, (
        "company profile is completely empty"
    )


# ── test 1: breadth across 5 companies ───────────────────────────────────────

class TestBreadth:
    """Scrape 5 different companies in parallel and assert correctness."""

    @pytest.fixture(scope="class")
    def results(self) -> list[ScrapeResult]:
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(_scrape, c["name"], c["url"]): c
                for c in COMPANIES
            }
            out = {}
            for future in as_completed(futures):
                c = futures[future]
                out[c["name"]] = future.result()
        return out

    def _summary(self, results: dict) -> str:
        lines = ["\n--- breadth results ---"]
        for name, r in results.items():
            status = "OK" if r.ok else "FAIL"
            lines.append(f"  [{status}] {name}  ({r.duration_s:.1f}s)"
                         + (f"  → {r.error.splitlines()[0]}" if r.error else ""))
        return "\n".join(lines)

    @pytest.mark.parametrize("company", COMPANIES, ids=[c["name"] for c in COMPANIES])
    def test_company(self, results: dict, company: dict) -> None:
        result = results[company["name"]]
        print(self._summary(results))
        _assert_page_valid(result, company["expected_currency"], company["expected_symbol"])
        print(
            f"  [{company['name']}] price={result.page.price.current:,.2f} {result.page.currency}"
            f"  tech={result.page.technical.overall_signal}"
            f"  news={len(result.page.news)}"
        )


# ── test 2: rate-limit stress (15 sequential requests to same URL) ───────────

class TestRateStress:
    """Hit the same URL 15 times back-to-back and check none are blocked."""

    @pytest.fixture(scope="class")
    def stress_results(self) -> list[ScrapeResult]:
        out = []
        for i in range(RATE_STRESS_N):
            r = _scrape(f"run {i+1}/{RATE_STRESS_N}", RATE_STRESS_URL, timeout=60)
            out.append(r)
            status = "OK" if r.ok else f"FAIL ({r.error.splitlines()[0] if r.error else '?'})"
            print(f"  run {i+1:2}/{RATE_STRESS_N}  {r.duration_s:.1f}s  {status}")
        return out

    def test_no_failures(self, stress_results: list[ScrapeResult]) -> None:
        failed = [r for r in stress_results if not r.ok]
        durations = [r.duration_s for r in stress_results]
        print(
            f"\n--- rate stress ({RATE_STRESS_N} sequential requests) ---\n"
            f"  ok={RATE_STRESS_N - len(failed)}  fail={len(failed)}\n"
            f"  duration min={min(durations):.1f}s  max={max(durations):.1f}s"
            f"  avg={sum(durations)/len(durations):.1f}s"
        )
        if failed:
            details = "\n".join(
                f"  run {i}: {r.error.splitlines()[0]}"
                for i, r in enumerate(stress_results)
                if not r.ok
            )
            pytest.fail(f"{len(failed)}/{RATE_STRESS_N} requests failed:\n{details}")

    def test_data_consistency(self, stress_results: list[ScrapeResult]) -> None:
        """Price and symbol must be consistent across all successful runs."""
        ok = [r for r in stress_results if r.ok]
        if len(ok) < 2:
            pytest.skip("too few successful runs to check consistency")

        symbols = {r.page.symbol for r in ok}
        assert len(symbols) == 1, f"symbol inconsistent across runs: {symbols}"

        prices = [r.page.price.current for r in ok]
        # Allow up to 5% spread (market could move between requests)
        spread = (max(prices) - min(prices)) / min(prices) if min(prices) else 0
        assert spread < 0.05, (
            f"price spread {spread:.1%} exceeds 5% across runs "
            f"(min={min(prices):,.2f} max={max(prices):,.2f}) — possible stale/blocked responses"
        )

    def test_no_degradation(self, stress_results: list[ScrapeResult]) -> None:
        """Later requests should not be dramatically slower (sign of throttling)."""
        ok = [r for r in stress_results if r.ok]
        if len(ok) < 5:
            pytest.skip("too few successful runs to check degradation")

        first_half  = ok[:len(ok) // 2]
        second_half = ok[len(ok) // 2:]
        avg_first  = sum(r.duration_s for r in first_half)  / len(first_half)
        avg_second = sum(r.duration_s for r in second_half) / len(second_half)

        print(f"\n  avg latency first-half={avg_first:.1f}s  second-half={avg_second:.1f}s")
        # Allow second half to be at most 3× slower than first
        assert avg_second < avg_first * 3 or avg_second < 30, (
            f"second-half requests ({avg_second:.1f}s avg) are much slower than "
            f"first-half ({avg_first:.1f}s avg) — possible rate throttling"
        )
