# FIFA Live Data Audit: FotMob vs Google

Polls FotMob's JSON API and Google's rendered score box for live World Cup
matches, diffs score and status with a latency tolerance window, and logs
snapshots plus findings to SQLite.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run

```bash
# Audit live matches (browser window visible, recommended)
python main.py

# Headless (riskier with Google)
python main.py --headless

# Print summary stats from audit.db
python main.py --report
```

One Chromium window opens with two tabs: tab 1 stays on FotMob's World Cup
fixtures page (which live-updates in place), tab 2 runs Google searches for
each live match. Leave the window open and visible while auditing.

## How findings are classified

- LATENCY: sources disagreed, then reconverged within 90 seconds.
  Duration is the measured lag; `laggard` says which source was behind.
- DISCREPANCY: a score disagreement persisted past 90 seconds.
- STATUS_MISMATCH: status (live/HT/FT) disagreement persisted past 90 seconds.
- RESOLVED: disagreed longer than the window but eventually reconverged.

Tune the window in `fifa_audit/comparator.py` (TOLERANCE_S).

## Useful queries

```sql
-- Lag distribution by laggard
SELECT laggard, COUNT(*), ROUND(AVG(duration_s),1), ROUND(MAX(duration_s),1)
FROM findings WHERE kind='latency' GROUP BY laggard;

-- Timeline for one match
SELECT datetime(observed_at,'unixepoch','localtime'), source,
       home_score||'-'||away_score, status, clock
FROM snapshots WHERE match_key LIKE '%Mexico%' ORDER BY observed_at;
```

## Caveats

- FotMob's JSON API now requires a signed token, so this reads the
  rendered fixtures page in a real browser tab instead. The row parser
  lives in fifa_audit/fotmob.py (parse_row) if their layout changes.
- Google scraping is fragile and against their ToS for automation. Run
  the browser headed, keep volume low, and if a CAPTCHA appears the tool
  backs off so you can solve it manually. Never automate CAPTCHA solving.
- Team name mismatches are handled in `fifa_audit/normalize.py`. Add
  aliases there when you see false "pairing" findings.


## Live dashboard (GitHub Pages)

The `docs/` folder is a self-contained, viewer-facing dashboard reporting
the accuracy of Google's live score box against the reference feed. It is
built for an external audience: it explains what the service does, what is
measured, and shows a green/amber/red verdict with an accuracy trend chart
and a findings log.

### One-time setup

```bash
# from the fifa-audit folder
git init && git add . && git commit -m "fifa audit agent + dashboard"
gh repo create fifa-score-audit --public --source . --push
```

Then in the repo on github.com: Settings > Pages > Source: "Deploy from a
branch" > Branch: main, folder: /docs. The dashboard goes live at
`https://<your-username>.github.io/fifa-score-audit/` within a minute or
two. Share that URL with anyone; it ships with sample data (banner shown)
until the agent publishes real results.

### Publishing live data

```bash
python main.py --publish
```

`--publish` writes `docs/data/audit.json` every cycle and git-pushes it
every 2 minutes (tune with `--push-every`). The page itself refetches the
data every 60 seconds, so external viewers are at most ~3 minutes behind
the live audit.

### How the verdict is computed

- Red card (action needed): a confirmed score error (>90s) in the last
  hour, or the latest 15-minute window dropped below 95% accuracy.
- Amber card (degrading): accuracy is trending down and below 99%, or
  median lag exceeds 60 seconds.
- Green card (healthy): everything else.

Thresholds live in `docs/index.html` (status logic) and
`fifa_audit/publisher.py` (trend math).
