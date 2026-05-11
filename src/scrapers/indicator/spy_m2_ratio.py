"""S&P 500 / M2 ratio — S&P 500 level from Yahoo Finance divided by M2 in trillions."""

from __future__ import annotations

from curl_cffi import requests as cf_requests
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.scrapers.indicator._fred import get_latest

_SP500_URL = "https://query2.finance.yahoo.com/v8/finance/chart/%5EGSPC"
_HEADERS = {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"}

# Historical reference points for qualitative label
_ELEVATED_THRESHOLD = 250   # S&P / M2(trn) > 250 is elevated
_COMPRESSED_THRESHOLD = 150  # < 150 is compressed


class SpyM2RatioResult(BaseModel):
    sp500_level: float
    m2_trn: float
    ratio: float   # sp500_level / m2_trn
    label: str     # "elevated", "neutral", or "compressed"
    date: str
    source: str = "Yahoo Finance ^GSPC / FRED M2SL"


class SpyM2RatioNode(ScrapingNode):
    def scrape(self) -> SpyM2RatioResult | None:
        return scrape_spy_m2_ratio()


def scrape_spy_m2_ratio() -> SpyM2RatioResult:
    session = cf_requests.Session(impersonate="chrome124")
    resp = session.get(_SP500_URL, params={"interval": "1d", "range": "5d"}, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    sp500 = float(meta.get("regularMarketPrice") or meta.get("previousClose"))

    d, m2_bln = get_latest("M2SL")
    m2_trn = m2_bln / 1000

    ratio = round(sp500 / m2_trn, 2)
    if ratio > _ELEVATED_THRESHOLD:
        label = "elevated"
    elif ratio < _COMPRESSED_THRESHOLD:
        label = "compressed"
    else:
        label = "neutral"

    return SpyM2RatioResult(
        sp500_level=round(sp500, 2),
        m2_trn=round(m2_trn, 3),
        ratio=ratio,
        label=label,
        date=d.isoformat(),
    )
