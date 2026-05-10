"""
Financial Times world news — article teasers from ft.com/world.

FT uses Akamai Bot Manager but curl_cffi chrome124 bypasses it.
No __NEXT_DATA__ — FT uses a custom SSR stack (n-express).
Article links follow /content/{uuid} pattern.
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.api.web_fetcher import fetch_html
from src.scrapers.base import ScrapingNode

_FT_BASE = "https://www.ft.com"
_WORLD_URL = f"{_FT_BASE}/world"
_UUID_RE = re.compile(r"/content/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class FTArticle(BaseModel):
    title: str
    url: str
    uuid: str
    section: str | None
    published_at: str | None
    teaser: str | None


class FTWorldResult(BaseModel):
    articles: list[FTArticle]
    count: int


class FTWorldNode(ScrapingNode):
    def scrape(self) -> FTWorldResult | None:
        return scrape_ft_world()


def scrape_ft_world(timeout: int = 30) -> FTWorldResult:
    html = fetch_html(_WORLD_URL, timeout=timeout)
    articles = _parse(html)
    return FTWorldResult(articles=articles, count=len(articles))


def _parse(html: str) -> list[FTArticle]:
    soup = BeautifulSoup(html, "html.parser")
    articles: list[FTArticle] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=_UUID_RE):
        href = link.get("href", "")
        m = _UUID_RE.search(href)
        if not m:
            continue
        uuid = m.group(1)
        if uuid in seen:
            continue
        seen.add(uuid)

        title = link.get_text(" ", strip=True)
        if not title:
            h = link.find(["h2", "h3", "h4"])
            title = h.get_text(strip=True) if h else ""
        if not title:
            continue

        url = _FT_BASE + href if href.startswith("/") else href

        # Walk up to find teaser container
        container = link
        for _ in range(6):
            p = container.parent
            if p is None:
                break
            classes = " ".join(p.get("class", []))
            if "o-teaser" in classes or "teaser" in p.get("data-trackable", "").lower():
                container = p
                break
            container = p

        teaser_el = container.find(class_=re.compile(r"standfirst|summary|teaser__body"))
        teaser = teaser_el.get_text(strip=True) if teaser_el else None

        tag_el = container.find(class_=re.compile(r"o-teaser__tag|teaser__tag"))
        section = tag_el.get_text(strip=True) if tag_el else None

        time_el = container.find("time")
        published_at = None
        if time_el:
            raw = time_el.get("datetime", "")
            published_at = raw if raw else time_el.get_text(strip=True)

        articles.append(FTArticle(
            title=title,
            url=url,
            uuid=uuid,
            section=section,
            published_at=published_at,
            teaser=teaser,
        ))

    return articles
