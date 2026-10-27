# Offline forensic triage of BALLDONTLIE date and score conflicts

When the private BALLDONTLIE import shows `date` vs New York `datetime`
differences, **do not** auto-shift the date. Multi-week/month gaps are not a
timezone conversion and may involve postponed fixtures or provider semantics.

`python -m betdoctore.season_triage` compares already downloaded, checksummed
sources with local results, **without any network calls or new API keys**.
It preserves the distinct upstream IDs, dates, final scores and source digests.
It never modifies historical data or clears approval/training locks.

Run from the clean `~/Documents/betdoctore-audit` worktree after pulling a
new head there; keep the original dirty checkout unchanged:

```sh
ROOT="$HOME/Documents/betdoctore"
AUDIT="$ROOT/data/coverage/approved/e1250411bc2f63ae4299be328782a159f6718ca13713212a5e0a89006ed38773.regular-season-audit.json"
"$HOME/Documents/betdoctore-audit/.venv/bin/python" -m betdoctore.season_triage \
  --root "$ROOT/data/results" \
  --reference "$ROOT/data/coverage/independent/balldontlie" \
  --audit "$AUDIT" \
  --output "$ROOT/data/coverage/triage" \
  --as-of 2026-10-27
```

The selected report is checked against its content-addressed SHA-256 filename.
The reference manifest digest must match the source receipt and audit; duplicate
IDs and altered timezone fields fail closed. The existing local snapshot is
reused; do not rerun the original 76-request acquisition.

Outputs (private/local only, immutable digest prefixes):
- `<digest>.summary.json`: aggregate distributions by completed season
- `<digest>.date-cases.json`: both dates and exact same-team/date candidates
- `<digest>.score-cases.json`: each score disagreement and source evidence
- `<digest>.triage.json`: full local audit

Candidate matching is based only on season, team pair and either exact date.
A single candidate is **not** proof of matching game identity; both dates
matching distinct scheduled games are `TWO_POSSIBLE_MATCH_DATES`.
Home disagreements remain separately flagged. Score conflicts are linked to
date quarantine only if the exact candidate game key matches. An absence of a
link does not prove the sets disjoint.

Known local baseline on 2026-10-27:
- 58 provider date conflicts: 36 / 19 / 3 for 2020–21 / 2021–22 / 2022–23
- 17 source score conflicts: 3 / 6 / 0 / 4 / 4 / 0 across 2020–21 to 2025–26
- 2025–26 has 1,230 single-source final scores, so cannot pass corroboration
- 0 independent approvals; source lineage rights/time and training gates BLOCKED

Treat all detailed outputs as private noncommercial research data; do not
upload fixture, Neil-Paine or provider raw data to GitHub or attach it to PRs.
