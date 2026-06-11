"""Team name normalization.

Most false positives in cross-source audits come from naming, not data.
Normalize both sources into a canonical key before comparing.
Extend ALIASES as you see real mismatches in the log.
"""

from __future__ import annotations

import re
import unicodedata

ALIASES = {
    "usa": "united states",
    "us": "united states",
    "united states of america": "united states",
    "korea republic": "south korea",
    "republic of korea": "south korea",
    "korea dpr": "north korea",
    "ir iran": "iran",
    "china pr": "china",
    "cote d'ivoire": "ivory coast",
    "côte d'ivoire": "ivory coast",
    "czechia": "czech republic",
    "türkiye": "turkey",
    "turkiye": "turkey",
    "bosnia-herzegovina": "bosnia and herzegovina",
}


def canon(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return ALIASES.get(s, s)


def same_team(a: str, b: str) -> bool:
    ca, cb = canon(a), canon(b)
    if ca == cb:
        return True
    # containment handles "iran" vs "ir iran" style residue
    return ca in cb or cb in ca
