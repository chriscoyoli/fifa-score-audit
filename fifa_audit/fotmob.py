"""FotMob data source (browser-based).

FotMob's JSON API now requires a signed request token, so rather than
calling it directly we read the rendered World Cup fixtures page in a
real browser tab. Match rows render as anchors whose text follows
stable line patterns:

  Finished:  Mexico / FT / 2 - 0 / South Africa
  Live:      South Korea / 63' / 1 - 0 / Czechia   (clock may be HT, 45+2')
  Scheduled: South Korea / 7:00 / PM / Czechia

The page live-updates over a socket, so after the first load we just
re-read the DOM each cycle instead of reloading.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import Snapshot

LEAGUE_URL = "https://www.fotmob.com/leagues/77/matches/fifa-world-cup"

SCORE_RE = re.compile(r"^(\d{1,2})\s*-\s*(\d{1,2})$")
CLOCK_RE = re.compile(r"^(\d{1,3})(?:\s*\+\s*\d{1,2})?['\u2019]$")
FT_TOKENS = {"FT", "AET", "FT (PEN)", "PEN", "AP"}


class FotMobSource:
    def __init__(self, page):
        self.page = page
        self._loaded = False

    def snapshot_all(self) -> list[Snapshot]:
        """Return one Snapshot per match row on the World Cup fixtures page."""
        if not self._loaded or LEAGUE_URL not in (self.page.url or ""):
            self.page.goto(LEAGUE_URL, timeout=25000)
            self.page.wait_for_timeout(2500)  # let hydration finish
            self._loaded = True

        snaps: dict[str, Snapshot] = {}
        for a in self.page.query_selector_all("a[href*='/matches/']"):
            href = a.get_attribute("href") or ""
            snap = parse_row(a.inner_text() or "")
            if snap is not None:
                snap.match_id = href
                snaps[href] = snap  # dedupe repeated anchors
        return list(snaps.values())


def parse_row(text: str) -> Optional[Snapshot]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 3:
        return None
    home, away = lines[0], lines[-1]
    middle = lines[1:-1]

    score: Optional[tuple[int, int]] = None
    status, clock = "scheduled", None
    for tok in middle:
        m = SCORE_RE.match(tok)
        if m:
            score = (int(m.group(1)), int(m.group(2)))
            continue
        up = tok.upper()
        if up in FT_TOKENS:
            status, clock = "ft", up
        elif up == "HT":
            status, clock = "ht", "HT"
        elif CLOCK_RE.match(tok):
            status, clock = "live", tok
    if score is not None and status == "scheduled":
        status = "live"  # score present but no recognizable clock token

    return Snapshot(
        source="fotmob", match_id="", home=home, away=away,
        home_score=score[0] if score else None,
        away_score=score[1] if score else None,
        status=status, clock=clock,
    )
