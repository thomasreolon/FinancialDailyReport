"""China Manufacturing PMI — NBS official and Caixin.

NBS PMI (official, state-sector heavy) and Caixin PMI (private/SME focus)
are the earliest monthly signals for Chinese industrial demand.
Both at 50 = neutral; above = expansion, below = contraction.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup
from pydantic import BaseModel

from src.scrapers.base import ScrapingNode
from src.api.web_fetcher import fetch_html

_TE_NBS_URL    = "https://tradingeconomics.com/china/manufacturing-pmi"
_TE_CAIXIN_URL = "https://tradingeconomics.com/china/caixin-manufacturing-pmi"


class ChinaPMIResult(BaseModel):
    nbs_mfg_pmi: float | None
    nbs_date: str | None
    caixin_mfg_pmi: float | None
    caixin_date: str | None
    source: str = "TradingEconomics (NBS / Caixin)"


class ChinaPMINode(ScrapingNode):
    def scrape(self) -> ChinaPMIResult | None:
        return scrape_china_pmi()


def _scrape_te_value(url: str) -> tuple[float, str] | None:
    """Scrape a single indicator value from TradingEconomics."""
    try:
        html = fetch_html(url, timeout=35)
        soup = BeautifulSoup(html, "html.parser")

        # TradingEconomics renders the current value in a few possible locations
        for sel in [
            "#ctl00_ContentPlaceHolder1_ctl00_lblIndexValue",
            "span.act-value",
            "#p",
        ]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True).replace(",", "")
                try:
                    val = float(text)
                    if 20 < val < 80:  # sanity range for PMI
                        return val, ""
                except ValueError:
                    pass

        # Fallback: look for a number near "Manufacturing PMI" text
        text = soup.get_text(" ")
        # Pattern: label followed by a decimal number in PMI range
        m = re.search(r"Manufacturing PMI[^\d]{0,30}(\d{2}\.\d)", text)
        if m:
            val = float(m.group(1))
            if 20 < val < 80:
                return val, ""

    except Exception:
        pass
    return None


def scrape_china_pmi() -> ChinaPMIResult:
    nbs_val = _scrape_te_value(_TE_NBS_URL)
    caixin_val = _scrape_te_value(_TE_CAIXIN_URL)

    return ChinaPMIResult(
        nbs_mfg_pmi=round(nbs_val[0], 1) if nbs_val else None,
        nbs_date=nbs_val[1] if nbs_val else None,
        caixin_mfg_pmi=round(caixin_val[0], 1) if caixin_val else None,
        caixin_date=caixin_val[1] if caixin_val else None,
    )
