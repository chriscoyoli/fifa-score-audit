"""Google score box extractor (browser-based).

Reads the rendered search results page for "<home> vs <away>". Text-pattern
parsing over the sports panel region, not CSS class names. If Google serves
a CAPTCHA or consent wall, raises BlockedError so the orchestrator backs
off; solve it manually in the visible browser window. Never automate
around CAPTCHAs.
"""

from __future__ import annotations

import re
from typing import Optional

from playwright.sync_api import TimeoutError as PWTimeout

from .models import Snapshot


class BlockedError(RuntimeError):
    pass


class GoogleScoreSource:
    def __init__(self, page):
        self.page = page

    def snapshot(self, home: str, away: str) -> Snapshot:
        query = f"{home} vs {away}"
        url = "https://www.google.com/search?q=" + re.sub(r"\s+", "+", query)
        self.page.goto(url, timeout=20000)

        if self._looks_blocked():
            raise BlockedError("Google served a CAPTCHA or consent interstitial")

        panel_text = self._sports_panel_text()
        score = _parse_score(panel_text)
        status, clock = _parse_status(panel_text)

        return Snapshot(
            source="google", match_id=f"g:{home}-{away}", home=home, away=away,
            home_score=score[0] if score else None,
            away_score=score[1] if score else None,
            status=status, clock=clock,
        )

    def _looks_blocked(self) -> bool:
        content = self.page.content().lower()
        return "unusual traffic" in content or "captcha" in content

    def _sports_panel_text(self) -> str:
        try:
            self.page.wait_for_selector("#search", timeout=8000)
        except PWTimeout:
            pass
        for selector in ("[class*='imso']", "#search"):
            el = self.page.query_selector(selector)
            if el:
                txt = el.inner_text()
                if txt and len(txt) > 20:
                    return txt
        return self.page.inner_text("body")


SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-:\u2013]\s*(\d{1,2})(?!\d)")
CLOCK_RE = re.compile(r"\b(\d{1,3})['\u2019]\s*(?:\+\s*\d+)?")


def _parse_score(text: str) -> Optional[tuple[int, int]]:
    m = SCORE_RE.search(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_status(text: str) -> tuple[str, Optional[str]]:
    upper = text.upper()
    if re.search(r"\bFULL[- ]?TIME\b|\bFT\b", upper):
        return "ft", "FT"
    if re.search(r"\bHALF[- ]?TIME\b|\bHT\b", upper):
        return "ht", "HT"
    m = CLOCK_RE.search(text)
    if m:
        return "live", f"{m.group(1)}'"
    if re.search(r"\bLIVE\b", upper):
        return "live", None
    return "scheduled", None
