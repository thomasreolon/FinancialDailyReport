"""
Multi-tier HTML fetcher with progressive anti-bot bypass strategies.

Tier 1: requests  — browser headers, fast (~60% of sites)
Tier 2: curl_cffi — TLS browser fingerprint impersonation (bypasses Cloudflare L1)
Tier 3: playwright stealth — headless JS rendering + navigator patches
Tier 4: playwright human  — randomised viewport, mouse movement, scroll delays
"""

from __future__ import annotations

import logging
import random
import time

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

_BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

_STEALTH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--lang=en-US,en",
]

_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
Object.defineProperty(navigator, 'permissions', {
    get: () => ({query: () => Promise.resolve({state: 'granted'})}),
});
"""

# Hard block signals: these always indicate a bot-wall, regardless of link count
_HARD_BLOCK_SIGNALS = [
    "checking your browser",
    "please wait... | cloudflare",
    "just a moment...",
    "enable javascript and cookies to continue",
    "cf-browser-verification",
    "ddos-guard",
    "you have been blocked",
    "please verify you are a human",
]

# Soft block signals: only indicate a block when the page has few real links
# (sites legitimately mention these in footers alongside real content)
_SOFT_BLOCK_SIGNALS = [
    "your privacy choices",
    "le tue scelte relative alla privacy",
    "before you continue to",
    "consent management platform",
    "manage your consent",
]


def _is_blocked(html: str) -> bool:
    if len(html) < 500:
        return True
    lower = html.lower()
    # Garbled / binary: real HTML always has structural tags
    if "<html" not in lower and "<body" not in lower and "<head" not in lower:
        return True
    if any(sig in lower for sig in _HARD_BLOCK_SIGNALS):
        return True
    # Soft signals only count when the page is sparse (consent wall, not footer mention)
    import re
    link_count = len(re.findall(r"<a[\s>]", lower))
    if link_count < 10 and any(sig in lower for sig in _SOFT_BLOCK_SIGNALS):
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: int = 30) -> str:
    """
    Download the fully rendered HTML of a webpage.

    Tries increasingly sophisticated anti-bot bypass techniques and returns the
    first response that is not a bot-block page.

    Args:
        url: The page URL.
        timeout: Per-tier timeout in seconds.

    Returns:
        HTML string.

    Raises:
        RuntimeError: If every tier is blocked or fails.
    """
    tiers = [
        ("requests",          _fetch_requests),
        ("curl_cffi",         _fetch_curl_cffi),
        ("playwright-stealth",_fetch_playwright_stealth),
        ("playwright-human",  _fetch_playwright_human),
        ("scraper.do",        _fetch_scrapedo),
    ]

    errors: list[str] = []
    for name, fn in tiers:
        try:
            logger.debug("Trying tier %s for %s", name, url)
            html = fn(url, timeout)
            if html and not _is_blocked(html):
                logger.info("Success via %s — %d chars from %s", name, len(html), url)
                return html
            errors.append(f"{name}: blocked/empty response ({len(html)} chars)")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.debug("Tier %s error: %s", name, exc)

    raise RuntimeError(
        f"All fetch tiers failed for {url}:\n" + "\n".join(f"  • {e}" for e in errors)
    )


# ---------------------------------------------------------------------------
# Tier 1: plain requests with browser headers
# ---------------------------------------------------------------------------

def _fetch_requests(url: str, timeout: int) -> str:
    import requests

    session = requests.Session()
    session.headers.update({
        **_BROWSER_HEADERS,
        "User-Agent": random.choice(_USER_AGENTS),
    })
    resp = session.get(url, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Tier 2: curl_cffi — TLS browser fingerprint impersonation
# Impersonates Chrome's TLS ClientHello, bypassing many Cloudflare checks.
# ---------------------------------------------------------------------------

def _fetch_curl_cffi(url: str, timeout: int) -> str:
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError as exc:
        raise RuntimeError("curl_cffi not installed") from exc

    resp = cffi_requests.get(
        url,
        impersonate="chrome124",
        headers={"User-Agent": random.choice(_USER_AGENTS)},
        timeout=timeout,
        allow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONSENT_ACCEPT_SELECTORS = [
    # Yahoo Finance / Oath consent
    'button[data-beacon*="AcceptAll"]',
    'button[name="agree"]',
    # Generic
    'button:has-text("Accept all")',
    'button:has-text("Accept All")',
    'button:has-text("I Accept")',
    'button:has-text("Agree")',
    'button:has-text("Allow all")',
    'button:has-text("Allow All")',
    '[id*="accept-all"]',
    '[class*="accept-all"]',
    '[id*="acceptAll"]',
]


def _dismiss_consent(page) -> bool:
    """Click an accept-all consent button if present. Returns True if clicked."""
    for sel in _CONSENT_ACCEPT_SELECTORS:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1000):
                btn.click()
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Tier 3: Playwright — headless Chromium with stealth patches
# Renders JS, patches navigator.webdriver and related fingerprints.
# ---------------------------------------------------------------------------

def _fetch_playwright_stealth(url: str, timeout: int) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=_STEALTH_ARGS + ["--window-size=1920,1080"],
        )
        ctx = browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        ctx.add_init_script(_STEALTH_INIT_SCRIPT)
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception:
            pass
        # Handle consent dialogs before grabbing final HTML
        if _dismiss_consent(page):
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
        html = page.content()
        browser.close()
    return html


# ---------------------------------------------------------------------------
# Tier 4: Playwright — human simulation (random viewport, mouse, scroll)
# For sites that detect headless timing or interaction patterns.
# ---------------------------------------------------------------------------

def _fetch_playwright_human(url: str, timeout: int) -> str:
    from playwright.sync_api import sync_playwright

    vw = random.randint(1280, 1920)
    vh = random.randint(800, 1080)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=_STEALTH_ARGS + [f"--window-size={vw},{vh}"],
        )
        ctx = browser.new_context(
            user_agent=random.choice(_USER_AGENTS),
            viewport={"width": vw, "height": vh},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        ctx.add_init_script(_STEALTH_INIT_SCRIPT)
        page = ctx.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception:
            pass

        # Handle consent dialogs
        if _dismiss_consent(page):
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass

        # Simulate human: pause, random mouse move, slow scroll
        time.sleep(random.uniform(1.5, 3.0))
        page.mouse.move(random.randint(200, vw - 200), random.randint(200, vh - 200))
        time.sleep(random.uniform(0.3, 0.7))
        page.evaluate("window.scrollBy({top: 300, behavior: 'smooth'})")
        time.sleep(random.uniform(0.8, 1.5))
        page.evaluate("window.scrollBy({top: 400, behavior: 'smooth'})")
        time.sleep(random.uniform(0.5, 1.2))

        # Let any lazy-loaded content settle
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass

        html = page.content()
        browser.close()
    return html


# ---------------------------------------------------------------------------
# Tier 5: scrape.do — managed residential-proxy + JS rendering API
# Last resort when all local tiers are blocked. Consumes API credits.
# Docs: https://scrape.do/docs  |  env var: SCRAPEDO_API_KEY
# ---------------------------------------------------------------------------

_SCRAPEDO_ENDPOINT = "https://api.scrape.do/"


def _fetch_scrapedo(url: str, timeout: int) -> str:
    import os
    import requests as _requests

    api_key = os.environ.get("SCRAPEDO_API_KEY")
    if not api_key:
        raise RuntimeError("SCRAPEDO_API_KEY not set")

    # Try JS-rendered first (more capable, costs more credits), then plain.
    for render in (True, False):
        params = {
            "token": api_key,
            "url": url,
            "render": "true" if render else "false",
            "country": "us",
        }
        resp = _requests.get(
            _SCRAPEDO_ENDPOINT,
            params=params,
            timeout=timeout + 30,  # scrape.do has its own internal timeout
        )
        if resp.status_code == 200:
            return resp.text
        if resp.status_code in (401, 403):
            raise RuntimeError(f"scrape.do auth error: HTTP {resp.status_code}")
        logger.debug("scrape.do render=%s → HTTP %s", render, resp.status_code)

    resp.raise_for_status()
    return resp.text  # unreachable
