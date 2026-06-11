"""FIFA live data audit: FotMob fixtures page vs Google score box.

Usage:
  python main.py              # audit live World Cup matches (visible browser)
  python main.py --headless   # run browser headless (riskier with Google)
  python main.py --report     # print summary from audit.db

Loop (every 30s):
  1. Read FotMob's World Cup fixtures page (tab 1) for the full slate.
  2. For each live match, read the Google score panel (tab 2).
  3. Diff via Comparator (90s latency tolerance), log all to SQLite.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from fifa_audit.browser import BrowserHub
from fifa_audit.comparator import Comparator
from fifa_audit.fotmob import FotMobSource
from fifa_audit.google_box import BlockedError, GoogleScoreSource
from fifa_audit.store import Store, log_check
from fifa_audit import publisher

POLL_INTERVAL_S = 30
BACKOFF_ON_BLOCK_S = 300


def run(headless: bool, publish: bool, push_every: int):
    store = Store()
    comp = Comparator()
    hub = BrowserHub(headless=headless)
    fm_src = FotMobSource(hub.new_page())
    gg_src = GoogleScoreSource(hub.new_page())
    last_push = 0.0
    print("Auditing live World Cup matches. Ctrl-C to stop.")

    try:
        while True:
            cycle_start = time.time()
            try:
                slate = fm_src.snapshot_all()
            except Exception as e:
                print(f"[fotmob] slate error: {e}", file=sys.stderr)
                time.sleep(POLL_INTERVAL_S)
                continue

            live = [s for s in slate if s.status in ("live", "ht")]
            if not live:
                print(f"{_now()} no live matches "
                      f"({len(slate)} rows on fixtures page)")
            for fm in live:
                store.log_snapshot(fm)
                try:
                    gg = gg_src.snapshot(fm.home, fm.away)
                except BlockedError:
                    print(f"{_now()} Google blocked us; backing off "
                          f"{BACKOFF_ON_BLOCK_S}s. If a CAPTCHA is visible "
                          f"in the browser window, solve it manually.")
                    time.sleep(BACKOFF_ON_BLOCK_S)
                    continue
                except Exception as e:
                    print(f"[google] {fm.home} vs {fm.away}: {e}",
                          file=sys.stderr)
                    continue
                store.log_snapshot(gg)
                log_check(
                    store, f"{fm.home} vs {fm.away}",
                    f"{fm.home_score}-{fm.away_score}",
                    f"{gg.home_score}-{gg.away_score}",
                    agree=(fm.home_score == gg.home_score
                           and fm.away_score == gg.away_score),
                )

                findings = comp.compare(fm, gg)
                for f in findings:
                    store.log_finding(f)
                    r = f.as_row()
                    print(f"{_now()} {r['kind'].upper():<15} "
                          f"{r['match']:<30} {r['field']}: "
                          f"fotmob={r['fotmob']} google={r['google']} "
                          f"dur={r['duration_s']}s lag={r['laggard']}")
                if not findings:
                    print(f"{_now()} OK {fm.home} {fm.home_score}-"
                          f"{fm.away_score} {fm.away} [{fm.clock}] "
                          f"google={gg.home_score}-{gg.away_score} "
                          f"[{gg.clock}]")

            if publish:
                publisher.export(store, "docs/data/audit.json")
                if push_every and time.time() - last_push > push_every:
                    if publisher.git_push():
                        last_push = time.time()
                        print(f"{_now()} published to GitHub")

            elapsed = time.time() - cycle_start
            time.sleep(max(5, POLL_INTERVAL_S - elapsed))
    except KeyboardInterrupt:
        print("\nStopping. Summary:")
        report(store)
    finally:
        hub.close()


def report(store: Store | None = None):
    store = store or Store()
    rows = store.summary()
    if not rows:
        print("No findings logged yet.")
        return
    print(f"{'kind':<16}{'field':<10}{'count':>6}{'avg_s':>8}{'max_s':>8}")
    for kind, field, n, avg_s, max_s in rows:
        print(f"{kind:<16}{field:<10}{n:>6}{avg_s or 0:>8}{max_s or 0:>8}")


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--headless", action="store_true")
    p.add_argument("--report", action="store_true")
    p.add_argument("--publish", action="store_true",
                   help="write docs/data/audit.json every cycle")
    p.add_argument("--push-every", type=int, default=120,
                   help="git push interval in seconds (with --publish)")
    args = p.parse_args()
    if args.report:
        report()
    else:
        run(args.headless, args.publish, args.push_every)
