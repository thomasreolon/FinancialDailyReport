"""
StoneX Financial Markets Morning Commentary scraper.

Cloudflare Turnstile blocks curl_cffi; Playwright tier in fetch_html() bypasses it.
Falls back to RSS feed if all page-fetch tiers fail.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.api.web_fetcher import fetch_html
from src.scrapers.base import ScrapingNode

_BASE = "https://www.stonex.com"
_RSS_CANDIDATES = [
    f"{_BASE}/en/insights/feed/",
    f"{_BASE}/feed/",
    f"{_BASE}/en/feed/",
    f"{_BASE}/en/insights/category/morning-commentary/feed/",
]
_RSS_HEADERS = {
    "Accept": "application/rss+xml,application/xml;q=0.9,text/xml;q=0.8,*/*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
}


class StoneXArticle(BaseModel):
    title: str | None
    date: str | None
    author: str | None
    url: str
    paragraphs: list[str]
    word_count: int


class StoneXResult(BaseModel):
    article: StoneXArticle | None
    source: str  # "page" or "rss"


class StoneXNode(ScrapingNode):
    def __init__(self, date: str | None = None):
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.date = date

    def scrape(self) -> StoneXResult | None:
        return scrape_stonex(self.date)


def scrape_stonex(date: str | None = None, timeout: int = 45) -> StoneXResult:
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"{_BASE}/en/insights/financial-markets-morning-commentary-{date}/"

    html = None
    try:
        html = fetch_html(url, timeout=timeout)
    except RuntimeError:
        pass

    if html:
        article = _parse_page(html, url)
        return StoneXResult(article=article, source="page")

    article = _try_rss(date)
    return StoneXResult(article=article, source="rss")


def _parse_page(html: str, url: str) -> StoneXArticle:
    soup = BeautifulSoup(html, "html.parser")

    title = None
    for sel in ["h1.entry-title", "h1.post-title", "h1.article-title", "h1"]:
        el = soup.select_one(sel)
        if el:
            title = el.get_text(strip=True)
            break

    date = None
    time_el = soup.find("time")
    if time_el:
        date = time_el.get("datetime") or time_el.get_text(strip=True)
    if not date:
        for prop in ["article:published_time", "datePublished"]:
            meta = soup.find("meta", {"property": prop}) or soup.find("meta", {"name": prop})
            if meta:
                date = meta.get("content", "").strip()
                break
    if not date:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", url)
        if m:
            date = m.group(1)

    author = None
    for sel in [".author-name", ".entry-author-name", 'a[rel="author"]', ".byline"]:
        el = soup.select_one(sel)
        if el:
            author = re.sub(r"^(by|author:?)\s+", "", el.get_text(strip=True), flags=re.I).strip()
            break
    if not author:
        meta = soup.find("meta", {"name": "author"})
        if meta:
            author = meta.get("content", "").strip()

    paragraphs: list[str] = []
    for sel in [".entry-content", ".post-content", ".article-content", ".article-body", "main"]:
        container = soup.select_one(sel)
        if container:
            items = container.find_all(["p", "li"])
            paragraphs = [el.get_text(" ", strip=True) for el in items if len(el.get_text(strip=True)) > 30]
            break

    word_count = sum(len(p.split()) for p in paragraphs)
    return StoneXArticle(title=title, date=date, author=author, url=url,
                         paragraphs=paragraphs, word_count=word_count)


def _try_rss(target_date: str) -> StoneXArticle | None:
    for rss_url in _RSS_CANDIDATES:
        try:
            resp = cf_requests.get(rss_url, impersonate="chrome124", headers=_RSS_HEADERS, timeout=20)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        if "<rss" not in resp.text and "<feed" not in resp.text:
            continue

        entries = _parse_rss(resp.text, target_date)
        if entries:
            entry = entries[0]
            content_html = entry.get("content") or entry.get("summary", "")
            link = entry.get("link", rss_url)
            article = _parse_page(content_html, link) if content_html else None
            if article:
                article.title = article.title or entry.get("title")
                article.date = article.date or entry.get("published")
                article.author = article.author or entry.get("author")
                article.url = link
            return article
    return None


def _parse_rss(xml_text: str, target_date: str) -> list[dict]:
    ns = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    channel = root.find("channel")
    items = channel.findall("item") if channel is not None else []
    entries = []
    for item in items:
        def _get(tag: str, prefix: str | None = None) -> str | None:
            uri = ns.get(prefix, "")
            el = item.find(f"{{{uri}}}{tag}" if prefix else tag)
            return (el.text or "").strip() if el is not None and el.text else None

        title = _get("title") or ""
        if "morning commentary" not in title.lower():
            continue

        entries.append({
            "title": title,
            "link": _get("link"),
            "published": _get("pubDate") or _get("date", "dc"),
            "author": _get("creator", "dc") or _get("author"),
            "summary": _get("description"),
            "content": _get("encoded", "content"),
        })

    return entries
