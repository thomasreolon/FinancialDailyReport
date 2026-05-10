"""
TIKR blog scraper — Next.js Pages Router (__NEXT_DATA__ JSON blob).

TIKR uses Next.js with getStaticProps/getServerSideProps so blog post data
is embedded in <script id="__NEXT_DATA__"> on the page — no HTML parsing needed.
curl_cffi chrome124 returns HTTP 200 with ~210KB HTML (no bot protection observed).
"""

import json
import re

from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode

_BASE = "https://www.tikr.com"
_BLOG_URL = f"{_BASE}/blog"
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}


class TIKRPost(BaseModel):
    title: str | None
    slug: str | None
    url: str | None
    date: str | None
    author: str | None
    category: str | None
    excerpt: str | None


class TIKRBlogResult(BaseModel):
    posts: list[TIKRPost]
    count: int
    source: str  # "next_data" or "html"


class TIKRBlogNode(ScrapingNode):
    def scrape(self) -> TIKRBlogResult | None:
        return scrape_tikr_blog()


def scrape_tikr_blog(timeout: int = 30) -> TIKRBlogResult:
    resp = cf_requests.get(
        _BLOG_URL,
        impersonate="chrome124",
        headers=_HEADERS,
        timeout=timeout,
        allow_redirects=True,
    )
    resp.raise_for_status()
    html = resp.text

    posts = _extract_from_next_data(html)
    if posts:
        return TIKRBlogResult(posts=posts, count=len(posts), source="next_data")

    posts = _parse_html_cards(html)
    return TIKRBlogResult(posts=posts, count=len(posts), source="html")


def _extract_from_next_data(html: str) -> list[TIKRPost]:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    page_props = data.get("props", {}).get("pageProps", {})

    raw_list: list[dict] = []
    for key in ("posts", "articles", "items", "blogs", "blogPosts", "data"):
        val = page_props.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            raw_list = val
            break
        if isinstance(val, dict):
            for sub in val.values():
                if isinstance(sub, list) and sub and isinstance(sub[0], dict):
                    raw_list = sub
                    break
            if raw_list:
                break

    return [_normalize_post(p) for p in raw_list]


def _normalize_post(p: dict) -> TIKRPost:
    title = p.get("title") or p.get("name")
    if isinstance(title, dict):
        title = title.get("rendered") or title.get("en")

    slug = p.get("slug") or p.get("id")
    url = p.get("url") or p.get("link") or (f"{_BLOG_URL}/{slug}" if slug else None)

    date = (p.get("publishedAt") or p.get("date") or p.get("createdAt") or "").split("T")[0] or None

    author = p.get("author")
    if isinstance(author, dict):
        author = author.get("name") or author.get("displayName")

    category = p.get("category") or p.get("categories")
    if isinstance(category, list):
        category = ", ".join(
            (c.get("name") if isinstance(c, dict) else str(c)) for c in category
        )
    elif isinstance(category, dict):
        category = category.get("name")

    excerpt = p.get("excerpt") or p.get("description") or p.get("summary")
    if isinstance(excerpt, dict):
        excerpt = excerpt.get("rendered") or excerpt.get("en")

    return TIKRPost(
        title=str(title) if title else None,
        slug=str(slug) if slug else None,
        url=str(url) if url else None,
        date=date,
        author=str(author) if author else None,
        category=str(category) if category else None,
        excerpt=str(excerpt)[:500] if excerpt else None,
    )


def _parse_html_cards(html: str) -> list[TIKRPost]:
    soup = BeautifulSoup(html, "html.parser")
    posts: list[TIKRPost] = []
    seen: set[str] = set()

    # TIKR renders blog posts as <a href="/blog/{slug}?"> containing all metadata
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "/blog/" not in href or "/category/" in href or "/author/" in href:
            continue
        url = href if href.startswith("http") else _BASE + href
        url = url.rstrip("?")
        if url in seen:
            continue
        seen.add(url)

        slug = url.rstrip("/").split("/blog/")[-1].split("?")[0]
        if not slug or "/" in slug:
            continue

        parts = [p.strip() for p in a_tag.get_text(separator="|", strip=True).split("|")
                 if p.strip() and p.strip() not in ("•", "Continue Reading", "Read More")]

        # Heuristic layout: [category, reading_time, title, author, date, excerpt]
        title = next((p for p in parts if len(p) > 20 and "minute" not in p.lower()), None)
        category = parts[0] if parts and len(parts[0]) < 40 else None

        date = None
        for p in parts:
            if re.match(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d", p):
                date = p
                break

        author = None
        for p in parts:
            if len(p) < 40 and p != category and p != date and "minute" not in p.lower() and p != title:
                author = p
                break

        excerpt = parts[-1] if parts and len(parts[-1]) > 60 else None

        posts.append(TIKRPost(title=title, slug=slug, url=url, date=date,
                               author=author, category=category, excerpt=excerpt))

    return posts
