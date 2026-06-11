"""SQLite audit log: every snapshot and every finding, queryable later."""

from __future__ import annotations

import json
import sqlite3

from .comparator import Finding
from .models import Snapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY,
  observed_at REAL, source TEXT, match_key TEXT,
  home_score INTEGER, away_score INTEGER, status TEXT, clock TEXT,
  raw JSON
);
CREATE TABLE IF NOT EXISTS findings (
  id INTEGER PRIMARY KEY,
  first_seen REAL, kind TEXT, match_key TEXT, field TEXT,
  fotmob TEXT, google TEXT, duration_s REAL, laggard TEXT
);
CREATE INDEX IF NOT EXISTS idx_snap_match ON snapshots(match_key, observed_at);
CREATE INDEX IF NOT EXISTS idx_find_match ON findings(match_key, first_seen);
CREATE TABLE IF NOT EXISTS checks (
  id INTEGER PRIMARY KEY,
  ts REAL, match_key TEXT,
  fotmob TEXT, google TEXT, agree INTEGER
);
CREATE INDEX IF NOT EXISTS idx_checks_ts ON checks(ts);
"""


class Store:
    def __init__(self, path: str = "audit.db"):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def log_snapshot(self, s: Snapshot):
        self.db.execute(
            "INSERT INTO snapshots (observed_at, source, match_key, home_score, "
            "away_score, status, clock, raw) VALUES (?,?,?,?,?,?,?,?)",
            (
                s.observed_at, s.source, f"{s.home} vs {s.away}",
                s.home_score, s.away_score, s.status, s.clock,
                json.dumps({"events": s.events}),
            ),
        )
        self.db.commit()

    def log_finding(self, f: Finding):
        r = f.as_row()
        self.db.execute(
            "INSERT INTO findings (first_seen, kind, match_key, field, fotmob, "
            "google, duration_s, laggard) VALUES (?,?,?,?,?,?,?,?)",
            (f.first_seen, r["kind"], r["match"], r["field"],
             r["fotmob"], r["google"], r["duration_s"], r["laggard"]),
        )
        self.db.commit()

    def summary(self) -> list[tuple]:
        return self.db.execute(
            "SELECT kind, field, COUNT(*), ROUND(AVG(duration_s),1), "
            "ROUND(MAX(duration_s),1) FROM findings GROUP BY kind, field"
        ).fetchall()


def log_check(store: "Store", match_key: str, fm_score: str, gg_score: str, agree: bool):
    import time as _t
    store.db.execute(
        "INSERT INTO checks (ts, match_key, fotmob, google, agree) VALUES (?,?,?,?,?)",
        (_t.time(), match_key, fm_score, gg_score, 1 if agree else 0),
    )
    store.db.commit()
