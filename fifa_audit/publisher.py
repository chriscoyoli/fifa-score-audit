"""Export audit.db into docs/data/audit.json for the dashboard,
and optionally git-push so GitHub Pages updates.

The dashboard is viewer-facing and score-focused: it reports how often
Google's score box agreed with the reference source (FotMob), how far
behind Google ran when it lagged, and any confirmed score errors.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .store import Store

WINDOW_HOURS = 24
BUCKET_S = 15 * 60


def export(store: Store, out_path: str, demo: bool = False) -> dict:
    now = time.time()
    since = now - WINDOW_HOURS * 3600

    checks = store.db.execute(
        "SELECT ts, match_key, fotmob, google, agree FROM checks WHERE ts >= ? ORDER BY ts",
        (since,),
    ).fetchall()

    findings = store.db.execute(
        "SELECT first_seen, kind, match_key, field, fotmob, google, duration_s, laggard "
        "FROM findings WHERE first_seen >= ? AND field='score' ORDER BY first_seen DESC LIMIT 50",
        (since,),
    ).fetchall()

    total = len(checks)
    agreed = sum(c[4] for c in checks)
    matches = sorted({c[1] for c in checks})

    lags = [f[6] for f in findings if f[1] == "latency" and f[7] == "google"]
    discrepancies = [f for f in findings if f[1] == "discrepancy"]
    label = {"google": "G", "fotmob": "FM"}
    behind_counts = {"G": 0, "FM": 0}
    for f in findings:
        if f[1] in ("latency", "resolved") and f[7] in label:
            behind_counts[label[f[7]]] += 1

    # 15-minute accuracy buckets
    buckets: dict[int, list[int]] = {}
    for ts, _, _, _, agree in checks:
        b = int(ts // BUCKET_S) * BUCKET_S
        buckets.setdefault(b, []).append(agree)
    trend = [
        {
            "bucket_start": _iso(b),
            "checks": len(v),
            "accuracy_pct": round(100 * sum(v) / len(v), 1),
        }
        for b, v in sorted(buckets.items())
    ]

    payload = {
        "generated_at": _iso(now),
        "demo": demo,
        "reference": "FM",
        "subject": "G live scores",
        "window_hours": WINDOW_HOURS,
        "tolerance_s": 90,
        "totals": {
            "checks": total,
            "agreed": agreed,
            "accuracy_pct": round(100 * agreed / total, 1) if total else None,
            "matches": len(matches),
            "score_discrepancies": len(discrepancies),
            "latency_events": len(lags),
            "median_lag_s": round(statistics.median(lags), 1) if lags else None,
            "max_lag_s": round(max(lags), 1) if lags else None,
            "behind_counts": behind_counts,
        },
        "trend": trend,
        "trend_direction": _trend_direction(trend),
        "findings": [
            {
                "ts": _iso(f[0]), "kind": f[1], "match": f[2],
                "truth": f[4], "observed": f[5],
                "duration_s": round(f[6], 1), "behind": {"google": "G", "fotmob": "FM"}.get(f[7], ""),
            }
            for f in findings
        ],
        "match_list": matches,
    }

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1))
    return payload


def _trend_direction(trend: list[dict]) -> str:
    """Compare mean accuracy of the latest 4 buckets vs the prior 4."""
    vals = [t["accuracy_pct"] for t in trend]
    if len(vals) < 4:
        return "flat"
    recent = vals[-4:]
    prior = vals[-8:-4] or vals[: len(vals) - 4]
    delta = (sum(recent) / len(recent)) - (sum(prior) / len(prior))
    if delta < -0.5:
        return "down"
    if delta > 0.5:
        return "up"
    return "flat"


def git_push(repo_dir: str = ".", paths: tuple = ("docs/data/audit.json",)) -> bool:
    """Commit and push the data file. Returns True on success.

    Requires the repo to already have a remote with push access configured
    (gh auth or an SSH key). Fails quietly so the audit loop keeps running.
    """
    try:
        subprocess.run(["git", "add", *paths], cwd=repo_dir, check=True,
                       capture_output=True)
        r = subprocess.run(
            ["git", "commit", "-m", f"audit data {_iso(time.time())}"],
            cwd=repo_dir, capture_output=True,
        )
        if r.returncode != 0:  # nothing to commit
            return True
        subprocess.run(["git", "push"], cwd=repo_dir, check=True,
                       capture_output=True, timeout=60)
        return True
    except Exception as e:
        print(f"[publish] git push failed: {e}")
        return False


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
