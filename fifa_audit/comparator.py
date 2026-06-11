"""Comparator and discrepancy engine.

Core idea: a raw mismatch at one instant is usually latency, not error.
So we track when a disagreement starts, and only escalate it to a true
DISCREPANCY if it persists beyond TOLERANCE_S. If the sources reconverge
within the window, we record it as LATENCY along with the measured lag,
which is often the most interesting audit output.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .models import Snapshot
from .normalize import same_team

TOLERANCE_S = 90  # how long a score disagreement may persist before it's an error


@dataclass
class Finding:
    kind: str            # "latency" | "discrepancy" | "resolved" | "status_mismatch"
    match_key: str
    field: str           # "score" | "status"
    fotmob_value: str
    google_value: str
    first_seen: float
    duration_s: float
    laggard: Optional[str] = None  # which source was behind, when knowable

    def as_row(self) -> dict:
        return {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.first_seen)),
            "kind": self.kind,
            "match": self.match_key,
            "field": self.field,
            "fotmob": self.fotmob_value,
            "google": self.google_value,
            "duration_s": round(self.duration_s, 1),
            "laggard": self.laggard or "",
        }


class Comparator:
    def __init__(self, tolerance_s: float = TOLERANCE_S):
        self.tolerance_s = tolerance_s
        # open disagreements keyed by (match_key, field)
        self._open: dict[tuple[str, str], dict] = {}
        # last agreed score per match, to infer which source moved first
        self._last_agreed: dict[str, tuple] = {}

    def compare(self, fm: Snapshot, gg: Snapshot) -> list[Finding]:
        if not (same_team(fm.home, gg.home) and same_team(fm.away, gg.away)):
            # pairing bug upstream; surface loudly rather than diffing garbage
            return [
                Finding(
                    kind="discrepancy",
                    match_key=f"{fm.home} vs {fm.away}",
                    field="pairing",
                    fotmob_value=f"{fm.home}/{fm.away}",
                    google_value=f"{gg.home}/{gg.away}",
                    first_seen=time.time(),
                    duration_s=0,
                )
            ]

        key = f"{fm.home} vs {fm.away}"
        now = time.time()
        findings: list[Finding] = []

        findings += self._check(
            key, "score", now,
            _fmt_score(fm), _fmt_score(gg),
            agree=(fm.home_score == gg.home_score and fm.away_score == gg.away_score),
            laggard=self._infer_laggard(key, fm, gg),
        )
        findings += self._check(
            key, "status", now,
            f"{fm.status} {fm.clock or ''}".strip(),
            f"{gg.status} {gg.clock or ''}".strip(),
            agree=(fm.status == gg.status),
            laggard=None,
        )

        if fm.home_score == gg.home_score and fm.away_score == gg.away_score:
            if fm.home_score is not None:
                self._last_agreed[key] = (fm.home_score, fm.away_score)

        return findings

    def _check(self, key, field, now, fm_val, gg_val, agree, laggard) -> list[Finding]:
        okey = (key, field)
        out: list[Finding] = []
        if agree:
            if okey in self._open:
                started = self._open.pop(okey)
                out.append(
                    Finding(
                        kind="latency" if (now - started["t0"]) <= self.tolerance_s else "resolved",
                        match_key=key, field=field,
                        fotmob_value=started["fm"], google_value=started["gg"],
                        first_seen=started["t0"], duration_s=now - started["t0"],
                        laggard=started.get("laggard"),
                    )
                )
            return out

        if okey not in self._open:
            self._open[okey] = {"t0": now, "fm": fm_val, "gg": gg_val,
                                "laggard": laggard, "escalated": False}
            return out

        st = self._open[okey]
        st["fm"], st["gg"] = fm_val, gg_val
        if not st["escalated"] and (now - st["t0"]) > self.tolerance_s:
            st["escalated"] = True
            out.append(
                Finding(
                    kind="discrepancy" if field == "score" else "status_mismatch",
                    match_key=key, field=field,
                    fotmob_value=fm_val, google_value=gg_val,
                    first_seen=st["t0"], duration_s=now - st["t0"],
                    laggard=st.get("laggard"),
                )
            )
        return out

    def _infer_laggard(self, key: str, fm: Snapshot, gg: Snapshot) -> Optional[str]:
        """If one source matches the last agreed score and the other moved on,
        the one still on the old score is the laggard."""
        last = self._last_agreed.get(key)
        if last is None:
            return None
        fm_cur = (fm.home_score, fm.away_score)
        gg_cur = (gg.home_score, gg.away_score)
        if fm_cur == last and gg_cur != last:
            return "fotmob"
        if gg_cur == last and fm_cur != last:
            return "google"
        return None


def _fmt_score(s: Snapshot) -> str:
    if s.home_score is None or s.away_score is None:
        return "?"
    return f"{s.home_score}-{s.away_score}"
