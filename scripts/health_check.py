"""
Health check for The Market Ledger — runs every scraper and reports status.

Exits with code 1 if any scraper FAIL so CI/agent runs can detect regressions.

Usage:
    python scripts/health_check.py                       # all scrapers (~5 min)
    python scripts/health_check.py --full                # + macro pipeline smoke test
    python scripts/health_check.py --live                # + live production server check
    python scripts/health_check.py --category indicator  # single category
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "output"
CATEGORIES = ["indicator", "news", "screener", "stock", "technical"]
PROD_URL = "https://report-server-rz3teebbga-ew.a.run.app"


# ── Status ───────────────────────────────────────────────────────────────────

class Status:
    OK   = "OK"
    WARN = "WARN"
    FAIL = "FAIL"

_ICON = {Status.OK: "✅", Status.WARN: "⚠️ ", Status.FAIL: "❌"}


# ── Result & Spec ─────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    category: str
    status: str = Status.OK
    value_str: str = "—"
    date_str: str = "—"
    age_days: int | None = None
    duration_s: float = 0.0
    warnings: list[str] = field(default_factory=list)
    error_type: str | None = None
    error_msg: str | None = None
    error_tb: str | None = None


@dataclass
class Spec:
    name: str
    category: str
    fn: Callable[[], Any]
    # extract(result) -> (value_str, date_str, warnings)
    extract: Callable[[Any], tuple[str, str, list[str]]]
    stale_after_days: int = 30  # warn when data is older than this
    none_ok: bool = False        # True = None return is sometimes expected, not a failure


@dataclass
class LiveCheckResult:
    status: str = Status.OK
    server_up: bool = False
    report_date: str = "—"
    age_days: int | None = None
    warnings: list[str] = field(default_factory=list)
    error_msg: str | None = None


# ── Runner ───────────────────────────────────────────────────────────────────

def _age_days(date_str: str) -> int | None:
    if not date_str or date_str == "—":
        return None
    try:
        return (date.today() - date.fromisoformat(date_str[:10])).days
    except ValueError:
        return None


def run_check(spec: Spec) -> CheckResult:
    r = CheckResult(name=spec.name, category=spec.category)
    t0 = time.perf_counter()
    try:
        result = spec.fn()
        r.duration_s = time.perf_counter() - t0

        if result is None:
            r.status = Status.WARN if spec.none_ok else Status.FAIL
            if spec.none_ok:
                r.warnings.append("returned None — no data available right now")
            else:
                r.error_type = "NoneResult"
                r.error_msg = "scraper returned None"
            return r

        try:
            r.value_str, r.date_str, warnings = spec.extract(result)
        except Exception as exc:
            r.status = Status.FAIL
            r.error_type = type(exc).__name__
            r.error_msg = f"extract() failed — possible model field change: {exc}"
            r.error_tb = traceback.format_exc()
            return r

        r.age_days = _age_days(r.date_str)
        r.warnings.extend(warnings)
        if r.age_days is not None and r.age_days > spec.stale_after_days:
            r.warnings.append(
                f"data is {r.age_days}d old (threshold: {spec.stale_after_days}d)"
                " — source may not have updated yet, or scraper is broken"
            )
        r.status = Status.WARN if r.warnings else Status.OK

    except Exception as exc:
        r.duration_s = time.perf_counter() - t0
        r.status = Status.FAIL
        r.error_type = type(exc).__name__
        r.error_msg = str(exc)
        r.error_tb = traceback.format_exc()

    return r


# ── Helpers ───────────────────────────────────────────────────────────────────

def _w(cond: bool, msg: str) -> list[str]:
    return [msg] if cond else []


# ── Scraper specs ─────────────────────────────────────────────────────────────

def _build_specs() -> list[Spec]:
    from src.scrapers.indicator.vix import scrape_vix
    from src.scrapers.indicator.fear_greed import scrape_fear_greed
    from src.scrapers.indicator.yield_curve import scrape_yield_curve
    from src.scrapers.indicator.fed_funds_rate import scrape_fed_funds_rate
    from src.scrapers.indicator.fed_june_probability import scrape_fed_june_probability
    from src.scrapers.indicator.fed_balance_sheet import scrape_fed_balance_sheet
    from src.scrapers.indicator.m2_us import scrape_m2_us
    from src.scrapers.indicator.global_m2 import scrape_global_m2
    from src.scrapers.indicator.rrp_facility import scrape_rrp_facility
    from src.scrapers.indicator.margin_debt import scrape_margin_debt
    from src.scrapers.indicator.spy_m2_ratio import scrape_spy_m2_ratio
    from src.scrapers.indicator.breakeven_5y import scrape_breakeven_5y
    from src.scrapers.indicator.breakeven_10y import scrape_breakeven_10y
    from src.scrapers.indicator.core_pce import scrape_core_pce
    from src.scrapers.indicator.ism_pmi import scrape_ism_pmi
    from src.scrapers.indicator.shiller_cape import scrape_shiller_cape
    from src.scrapers.indicator.buffett_indicator import scrape_buffett_indicator
    from src.scrapers.indicator.equity_risk_premium import scrape_equity_risk_premium
    from src.scrapers.indicator.lei import scrape_lei
    from src.scrapers.indicator.copper_gold_ratio import scrape_copper_gold_ratio
    from src.scrapers.indicator.sp500_fwd_eps import scrape_sp500_fwd_eps
    from src.scrapers.indicator.sp500_fwd_pe import scrape_sp500_fwd_pe
    from src.scrapers.indicator.sp500_eps_growth import scrape_sp500_eps_growth
    from src.scrapers.indicator.eurostoxx50_fwd_eps import scrape_eurostoxx50_fwd_eps
    from src.scrapers.indicator.leading_sectors import scrape_leading_sectors
    from src.scrapers.news.ft_world import scrape_ft_world
    from src.scrapers.news.stonex import scrape_stonex
    from src.scrapers.news.tikr_blog import scrape_tikr_blog
    from src.scrapers.news.yt_scraper import YTScraper
    from src.scrapers.screener.investing import scrape_mid_cap_losers
    from src.scrapers.screener.yahoo_trending import scrape_yahoo_trending
    from src.scrapers.screener.portfoliopilot import scrape_portfoliopilot
    from src.scrapers.screener.marketbeat_golden_cross import scrape_golden_cross
    from src.scrapers.stock.yahoo import scrape_yahoo_profile
    from src.scrapers.analyst.anachart import scrape_anachart
    from src.scrapers.analyst.marketbeat import scrape_marketbeat_forecast
    from src.scrapers.technical.market_overview import scrape_market_overview
    from src.scrapers.technical.sentiment_outlook import scrape_sentiment_outlook

    return [
        # ── Macro Indicators ──────────────────────────────────────────────────
        Spec("vix", "indicator", scrape_vix,
             lambda r: (f"{r.value:.2f}", r.date,
                        _w(not 5 < r.value < 80, f"value {r.value} outside expected range [5, 80]")),
             stale_after_days=3),
        Spec("fear_greed", "indicator", scrape_fear_greed,
             lambda r: (f"{r.score:.1f} {r.rating}", r.date,
                        _w(not 0 <= r.score <= 100, f"score {r.score} out of [0, 100]")),
             stale_after_days=3),
        Spec("yield_curve", "indicator", scrape_yield_curve,
             lambda r: (f"{r.spread_pct:+.3f}%", r.date,
                        _w(not -5 < r.spread_pct < 5, f"spread {r.spread_pct} looks wrong")),
             stale_after_days=5),
        Spec("fed_funds_rate", "indicator", scrape_fed_funds_rate,
             lambda r: (f"{r.rate_pct:.2f}%", r.date,
                        _w(not 0 <= r.rate_pct <= 25, f"rate {r.rate_pct} out of [0, 25]")),
             stale_after_days=5),
        Spec("fed_june_probability", "indicator", scrape_fed_june_probability,
             lambda r: (f"cut:{r.cut_25bp_pct}% hold:{r.hold_pct}%", r.meeting_date, []),
             none_ok=True, stale_after_days=7),
        Spec("fed_balance_sheet", "indicator", scrape_fed_balance_sheet,
             lambda r: (f"${r.value_trn:.2f}T", r.date,
                        _w(not 4 < r.value_trn < 20, f"value {r.value_trn}T out of [4, 20]")),
             stale_after_days=10),
        Spec("m2_us", "indicator", scrape_m2_us,
             lambda r: (
                 f"${r.value_trn:.2f}T YoY:{r.yoy_pct:+.1f}%" if r.yoy_pct else f"${r.value_trn:.2f}T",
                 r.date, _w(not 15 < r.value_trn < 35, f"M2 {r.value_trn}T out of [15, 35]"),
             ), stale_after_days=45),
        Spec("global_m2", "indicator", scrape_global_m2,
             lambda r: (f"${r.value_trn:.2f}T", r.date,
                        _w(not 60 < r.value_trn < 250, f"global M2 {r.value_trn}T out of [60, 250]")),
             stale_after_days=30),
        Spec("rrp_facility", "indicator", scrape_rrp_facility,
             lambda r: (f"${r.value_bln:.0f}B", r.date,
                        _w(r.value_bln < 0, "negative RRP balance")),
             stale_after_days=3),
        Spec("margin_debt", "indicator", scrape_margin_debt,
             lambda r: (f"${r.value_bln:.0f}B", r.date,
                        _w(not 200 < r.value_bln < 2000, f"margin debt {r.value_bln}B out of [200, 2000]")),
             none_ok=True, stale_after_days=45),
        Spec("spy_m2_ratio", "indicator", scrape_spy_m2_ratio,
             lambda r: (f"{r.ratio:.1f} ({r.label})", r.date,
                        _w(not 0 < r.ratio < 1000, f"ratio {r.ratio} looks wrong")),
             stale_after_days=3),
        Spec("breakeven_5y", "indicator", scrape_breakeven_5y,
             lambda r: (f"{r.rate_pct:.2f}%", r.date,
                        _w(not 0 < r.rate_pct < 8, f"rate {r.rate_pct} out of [0, 8]")),
             stale_after_days=5),
        Spec("breakeven_10y", "indicator", scrape_breakeven_10y,
             lambda r: (f"{r.rate_pct:.2f}%", r.date,
                        _w(not 0 < r.rate_pct < 8, f"rate {r.rate_pct} out of [0, 8]")),
             stale_after_days=5),
        Spec("core_pce", "indicator", scrape_core_pce,
             lambda r: (
                 f"{r.yoy_pct:.1f}%" if r.yoy_pct else "—", r.date,
                 _w(r.yoy_pct is not None and not 0 < r.yoy_pct < 20, f"PCE {r.yoy_pct} out of [0, 20]"),
             ), stale_after_days=45),
        Spec("ism_pmi", "indicator", scrape_ism_pmi,
             lambda r: (f"{r.value:.1f}", r.date,
                        _w(not 20 < r.value < 70, f"PMI {r.value} out of [20, 70]")),
             stale_after_days=35),
        Spec("shiller_cape", "indicator", scrape_shiller_cape,
             lambda r: (f"{r.value:.1f}x", r.date,
                        _w(not 10 < r.value < 60, f"CAPE {r.value} out of [10, 60]")),
             stale_after_days=35),
        Spec("buffett_indicator", "indicator", scrape_buffett_indicator,
             lambda r: (f"{r.ratio_pct:.1f}%", r.date,
                        _w(not 50 < r.ratio_pct < 500, f"Buffett {r.ratio_pct}% out of [50, 500]")),
             stale_after_days=35),
        Spec("equity_risk_premium", "indicator", scrape_equity_risk_premium,
             lambda r: (
                 f"{r.erp_pct:+.2f}%" if r.erp_pct else f"real_yield={r.real_yield_10y}% (fwd_PE unavailable)",
                 r.date,
                 _w(r.erp_pct is not None and not -10 < r.erp_pct < 20, f"ERP {r.erp_pct} looks wrong"),
             ), stale_after_days=5),
        Spec("lei", "indicator", scrape_lei,
             lambda r: (
                 f"{r.value:.3f} MoM:{r.mom_pct:+.2f}%" if r.mom_pct else f"{r.value:.3f}",
                 r.date, [],
             ), none_ok=True, stale_after_days=45),
        Spec("copper_gold_ratio", "indicator", scrape_copper_gold_ratio,
             lambda r: (f"{r.ratio:.5f}", r.date,
                        _w(not 0.00001 < r.ratio < 0.05, f"ratio {r.ratio} looks wrong")),
             stale_after_days=3),
        Spec("sp500_fwd_eps", "indicator", scrape_sp500_fwd_eps,
             lambda r: (f"${r.fwd_eps:.2f} ({r.fiscal_year})", r.date,
                        _w(not 50 < r.fwd_eps < 500, f"EPS ${r.fwd_eps} out of [50, 500]")),
             stale_after_days=14),
        Spec("sp500_fwd_pe", "indicator", scrape_sp500_fwd_pe,
             lambda r: (f"{r.fwd_pe:.1f}x", r.date,
                        _w(not 5 < r.fwd_pe < 50, f"P/E {r.fwd_pe} out of [5, 50]")),
             stale_after_days=3),
        Spec("sp500_eps_growth", "indicator", scrape_sp500_eps_growth,
             lambda r: (f"{r.growth_pct:+.1f}% ({r.quarter})", r.date, []),
             stale_after_days=90),
        Spec("eurostoxx50_fwd_eps", "indicator", scrape_eurostoxx50_fwd_eps,
             lambda r: (f"{r.growth_pct:+.1f}% ({r.fiscal_year})", r.date, []),
             stale_after_days=35),
        Spec("leading_sectors", "indicator", scrape_leading_sectors,
             lambda r: (
                 ", ".join(f"{s['sector']} {s.get('eps_growth_pct', '?')}%" for s in r.sectors[:2]),
                 r.date, _w(not r.sectors, "no sectors found"),
             ), stale_after_days=90),

        # ── News ─────────────────────────────────────────────────────────────
        Spec("ft_world", "news", scrape_ft_world,
             lambda r: (f"{r.count} articles", "—",
                        _w(r.count == 0, "zero articles — selector may have changed")),
             stale_after_days=999),
        Spec("stonex", "news", scrape_stonex,
             lambda r: (
                 f"{r.article.word_count} words" if r.article else "no article found",
                 "—",
                 _w(r.article is None, "no article — URL pattern or HTML structure may have changed"),
             ), stale_after_days=999),
        Spec("tikr_blog", "news", scrape_tikr_blog,
             lambda r: (f"{r.count} posts", "—",
                        _w(r.count == 0, "zero posts — selector may have changed")),
             stale_after_days=999),
        Spec("yt_fxevolution", "news",
             lambda: YTScraper(hours=72, channel="@fxevolutionvideo").scrape(),
             lambda r: (f"{len(r.transcript)} chars", "—",
                        _w(len(r.transcript) < 100, "transcript suspiciously short")),
             none_ok=True, stale_after_days=999),

        # ── Screeners ────────────────────────────────────────────────────────
        Spec("mid_cap_losers", "screener", lambda: scrape_mid_cap_losers(limit=5),
             lambda r: (f"{len(r.rows)} rows (of {r.total_in_universe})", "—",
                        _w(len(r.rows) == 0, "no rows — screener page may have changed")),
             stale_after_days=999),
        Spec("yahoo_trending", "screener", lambda: scrape_yahoo_trending(count=10),
             lambda r: (f"{r.count} tickers", "—",
                        _w(r.count == 0, "zero tickers")),
             stale_after_days=999),
        Spec("portfoliopilot", "screener", scrape_portfoliopilot,
             lambda r: (f"{len(r.stocks)} stocks", "—",
                        _w(len(r.stocks) == 0, "no stocks")),
             stale_after_days=999),
        Spec("golden_cross", "screener", scrape_golden_cross,
             lambda r: (f"{r.total} stocks", "—",
                        _w(r.total == 0, "no stocks")),
             stale_after_days=999),

        # ── Stock & Analyst (AAPL as representative sample) ───────────────────
        Spec("yahoo_AAPL", "stock", lambda: scrape_yahoo_profile("AAPL"),
             lambda r: (
                 f"${r.price:.2f}" if r.price else "no price",
                 "—",
                 _w(not r.price or r.price <= 0, "price missing or zero")
                 + _w(not r.exchange, "exchange field missing"),
             ), stale_after_days=999),
        Spec("anachart_AAPL", "stock", lambda: scrape_anachart("AAPL"),
             lambda r: (f"{r.count} ratings", "—",
                        _w(r.count == 0, "no analyst ratings")),
             stale_after_days=999),
        Spec("marketbeat_AAPL", "stock", lambda: scrape_marketbeat_forecast("AAPL", "NASDAQ"),
             lambda r: (
                 f"{r.consensus.overall} ({r.analyst_count} analysts)" if r.consensus else "no consensus",
                 "—",
                 _w(r.analyst_count == 0, "zero analysts"),
             ), stale_after_days=999),

        # ── Technical ────────────────────────────────────────────────────────
        Spec("market_overview", "technical", scrape_market_overview,
             lambda r: (f"{len(r.groups)} ETF groups", "—",
                        _w(len(r.groups) == 0, "no ETF groups")),
             stale_after_days=999),
        Spec("sentiment_outlook", "technical", scrape_sentiment_outlook,
             lambda r: (f"{r.count} entries", "—",
                        _w(r.count == 0, "no sentiment entries")),
             stale_after_days=999),
    ]


# ── Pipeline smoke test ───────────────────────────────────────────────────────

def run_smoke_test() -> dict:
    """Run the macro_indicators pipeline end-to-end (includes Gemini fill)."""
    try:
        from src.pipelines.macro_indicators import run_pipeline
        print("\n  Running macro_indicators pipeline (Gemini API call)...")
        result = run_pipeline()
        data = result.model_dump()
        meta_fields = {"gemini_filled", "fetched_at", "data_dates"}
        values = {k: v for k, v in data.items() if k not in meta_fields}
        total = len(values)
        non_null = sum(1 for v in values.values() if v is not None)
        null_fields = [k for k, v in values.items() if v is None]
        return {
            "total_fields": total,
            "non_null_fields": non_null,
            "gemini_filled": result.gemini_filled,
            "still_null": null_fields,
        }
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"}


# ── Live server check ─────────────────────────────────────────────────────────

def check_live_server() -> LiveCheckResult:
    """Hit the production Cloud Run URL and validate freshness + section completeness."""
    import urllib.error
    import urllib.request

    r = LiveCheckResult()

    def _get(path: str, timeout: int = 15) -> dict:
        with urllib.request.urlopen(f"{PROD_URL}{path}", timeout=timeout) as resp:
            import json
            return json.loads(resp.read())

    # 1. /health — basic reachability
    try:
        health = _get("/health", timeout=10)
        if health.get("status") != "ok":
            r.status = Status.FAIL
            r.error_msg = f"/health returned unexpected body: {health}"
            return r
        r.server_up = True
    except Exception as exc:
        r.status = Status.FAIL
        r.error_msg = f"server unreachable: {exc}"
        return r

    # 2. /api/latest — fetch the latest report JSON
    try:
        data = _get("/api/latest", timeout=20)
    except Exception as exc:
        r.status = Status.FAIL
        r.error_msg = f"/api/latest failed: {exc}"
        return r

    report = data.get("report", {})

    # 3. Freshness — warn if older than 3 days (covers weekends)
    generated_at = report.get("generated_at", "")
    if generated_at:
        r.report_date = generated_at[:10]
        r.age_days = (date.today() - date.fromisoformat(r.report_date)).days
        if r.age_days > 3:
            r.warnings.append(
                f"report is {r.age_days}d old (generated {r.report_date})"
                " — pipeline may not have run recently"
            )
    else:
        r.warnings.append("generated_at missing from report")

    # 4. Section completeness — each field is expected to be non-empty on a good run
    for field_name, label in [
        ("title",      "main article title"),
        ("article",    "main article body"),
        ("companies",  "company reports"),
        ("indicators", "macro indicators"),
        ("variations", "asset variations"),
    ]:
        if not report.get(field_name):
            r.warnings.append(f"'{field_name}' ({label}) is missing or empty")

    r.status = Status.WARN if r.warnings else Status.OK
    return r


# ── Report rendering ──────────────────────────────────────────────────────────

def _fmt_age(age: int | None) -> str:
    if age is None:
        return "—"
    return "today" if age == 0 else f"{age}d ago"


def _render_report(
    results: list[CheckResult],
    run_at: str,
    elapsed: float,
    smoke: dict | None,
    live: LiveCheckResult | None = None,
) -> str:
    ok   = sum(1 for r in results if r.status == Status.OK)
    warn = sum(1 for r in results if r.status == Status.WARN)
    fail = sum(1 for r in results if r.status == Status.FAIL)

    lines: list[str] = [
        "# The Market Ledger — Health Check",
        f"**{run_at}** — {len(results)} scrapers in {elapsed:.1f}s",
        "",
        f"**Summary:** ✅ {ok} OK  ⚠️  {warn} WARN  ❌ {fail} FAIL",
        "",
    ]

    by_cat: dict[str, list[CheckResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    for cat in CATEGORIES:
        cat_results = by_cat.get(cat, [])
        if not cat_results:
            continue
        cat_elapsed = sum(r.duration_s for r in cat_results)
        lines += [
            f"## {cat.title()} ({len(cat_results)} scrapers, {cat_elapsed:.1f}s)",
            "",
            "| Status | Scraper | Value | Date | Age | Duration |",
            "|--------|---------|-------|------|-----|----------|",
        ]
        for r in cat_results:
            lines.append(
                f"| {_ICON[r.status]} | `{r.name}` | {r.value_str} | {r.date_str}"
                f" | {_fmt_age(r.age_days)} | {r.duration_s:.1f}s |"
            )
        lines.append("")

    problems = [r for r in results if r.status != Status.OK]
    if problems:
        lines += ["## Issues", ""]
        for r in problems:
            lines.append(f"### {_ICON[r.status]} `{r.name}`")
            for w in r.warnings:
                lines.append(f"- ⚠️  {w}")
            if r.error_type:
                lines.append(f"- **Error:** `{r.error_type}` — {r.error_msg}")
            if r.error_tb:
                lines += ["", "```", r.error_tb.strip(), "```"]
            lines.append("")

    if smoke is not None:
        lines += ["## Pipeline Smoke Test (--full)", ""]
        if smoke.get("error"):
            lines += [f"❌ **FAILED:**", "```", smoke["error"].strip(), "```"]
        else:
            pct = smoke["non_null_fields"] / smoke["total_fields"] * 100
            lines += [
                f"✅ macro_indicators pipeline completed",
                f"- **Fields populated:** {smoke['non_null_fields']}/{smoke['total_fields']} ({pct:.0f}%)",
                f"- **Gemini-filled:** {smoke['gemini_filled']}",
            ]
            if smoke.get("still_null"):
                lines.append(f"- **Still null (check scrapers + Gemini fill):** {smoke['still_null']}")
        lines.append("")

    if live is not None:
        icon = _ICON[live.status]
        lines += [f"## Live Server Check (--live)", ""]
        if live.error_msg:
            lines += [f"{icon} **{live.error_msg}**", ""]
        else:
            age_str = f"{live.age_days}d ago" if live.age_days else "—"
            lines += [
                f"{icon} `{PROD_URL}`",
                f"- **Report date:** {live.report_date} ({age_str})",
            ]
            for w in live.warnings:
                lines.append(f"- ⚠️  {w}")
        lines.append("")

    return "\n".join(lines)


# ── Execution ─────────────────────────────────────────────────────────────────

def _run_parallel(specs: list[Spec]) -> list[CheckResult]:
    with ThreadPoolExecutor(max_workers=min(len(specs), 8)) as pool:
        futures = {pool.submit(run_check, spec): spec for spec in specs}
        done: dict[str, CheckResult] = {}
        for future in as_completed(futures):
            r = future.result()
            done[r.name] = r
    return [done[s.name] for s in specs]  # preserve registration order


def main() -> None:
    parser = argparse.ArgumentParser(description="Health check for The Market Ledger scrapers.")
    parser.add_argument("--full", action="store_true",
                        help="Also run macro pipeline smoke test (costs a Gemini API call).")
    parser.add_argument("--live", action="store_true",
                        help="Also check the live production server for freshness and completeness.")
    parser.add_argument("--category", choices=CATEGORIES,
                        help="Run only one category.")
    args = parser.parse_args()

    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"The Market Ledger — Health Check — {run_at}\n")

    specs = _build_specs()
    if args.category:
        specs = [s for s in specs if s.category == args.category]

    by_cat: dict[str, list[Spec]] = {}
    for s in specs:
        by_cat.setdefault(s.category, []).append(s)

    t0 = time.perf_counter()
    all_results: list[CheckResult] = []

    for cat in CATEGORIES:
        cat_specs = by_cat.get(cat, [])
        if not cat_specs:
            continue
        print(f"── {cat.title()} ({len(cat_specs)}) ──────────────────────────────")
        cat_results = _run_parallel(cat_specs)
        for r in cat_results:
            age = f"  {_fmt_age(r.age_days)}" if r.age_days is not None else ""
            print(f"  {_ICON[r.status]}  {r.name:<28} {r.value_str:<22} {r.date_str}{age}")
            for w in r.warnings:
                print(f"       ⚠️   {w}")
            if r.error_msg:
                print(f"       ✗   {r.error_msg}")
        all_results.extend(cat_results)
        print()

    smoke: dict | None = None
    if args.full:
        smoke = run_smoke_test()
        if smoke.get("error"):
            print(f"❌ pipeline smoke test FAILED:\n{smoke['error']}")
        else:
            pct = smoke["non_null_fields"] / smoke["total_fields"] * 100
            print(f"✅ pipeline: {smoke['non_null_fields']}/{smoke['total_fields']} fields ({pct:.0f}%)")
            if smoke["gemini_filled"]:
                print(f"   Gemini filled: {smoke['gemini_filled']}")
            if smoke.get("still_null"):
                print(f"   Still null: {smoke['still_null']}")
        print()

    live: LiveCheckResult | None = None
    if args.live:
        print("── Live Server ──────────────────────────────────────────")
        live = check_live_server()
        icon = _ICON[live.status]
        if live.error_msg:
            print(f"  {icon}  {live.error_msg}")
        else:
            age_str = f"{live.age_days}d ago" if live.age_days is not None else "—"
            print(f"  {icon}  server up  |  report: {live.report_date} ({age_str})")
            for w in live.warnings:
                print(f"       ⚠️   {w}")
        print()

    elapsed = time.perf_counter() - t0
    ok   = sum(1 for r in all_results if r.status == Status.OK)
    warn = sum(1 for r in all_results if r.status == Status.WARN)
    fail = sum(1 for r in all_results if r.status == Status.FAIL)
    print(f"{'─' * 58}")
    print(f"  ✅ {ok} OK   ⚠️  {warn} WARN   ❌ {fail} FAIL   ({len(all_results)} total, {elapsed:.1f}s)")

    OUTPUT_DIR.mkdir(exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = OUTPUT_DIR / f"health_{date_str}.md"
    out_path.write_text(_render_report(all_results, run_at, elapsed, smoke, live))
    print(f"  Report → {out_path.relative_to(ROOT)}")

    live_fail = live is not None and live.status == Status.FAIL
    if fail > 0 or live_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
