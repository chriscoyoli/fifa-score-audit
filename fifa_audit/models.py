"""Shared data model."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Snapshot:
    """A point-in-time observation of one match from one source."""

    source: str                 # "fotmob" or "google"
    match_id: str               # source-native id or href
    home: str
    away: str
    home_score: Optional[int]
    away_score: Optional[int]
    status: str                 # "scheduled" | "live" | "ht" | "ft" | "unknown"
    clock: Optional[str]        # e.g. "63'" or "HT"
    observed_at: float = field(default_factory=time.time)
    events: list = field(default_factory=list)
