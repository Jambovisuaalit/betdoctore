# Independent Wayback score-history capture evidence: follow-up

Historical NBA totals evaluation remains frozen at 14 exploratory development
games. The 18 independently verified schedule captures exposed 363 future,
unscored schedule candidates (February–April 2024, November 2024–April 2025),
but none of the **six previously downloaded score-history snapshots**
satisfies the strict seven-day age requirement at these future-game T−60
cutoffs. No new score-only regression, Random Forest or GCN training was run.

## Important audit discovery: monthly index collapse

The original `availability-acquire` implementation queried the public
Internet Archive CDX with `collapse=timestamp:6`, yielding **at most one
snapshot per month per original URL**. A six-snapshot local inventory
therefore is **not a complete test for weekly score-history coverage**.
It is not evidence that all candidate weeks lack a historical snapshot.

The standalone `python -m betdoctore.point_in_time_history` queries the
previously pinned Neil Paine raw CSV source at the **exact original URL**
with `from`, `to`, `filter=statuscode:200`, **without timestamp
collapse**, in the window from seven days before the earliest candidate's
scheduled T−60 through the latest candidate's scheduled T−60. It validates
CDX fields, source/mimetype/date bounds, truncation and identity; writes
the full CDX JSON (SHA-256), a hash-addressed **private** preview and a
summary. This phase reads **no NBA score rows or target results**.

Execute locally after updating the clean PR #2 worktree:

```sh
ROOT="$HOME/Documents/betdoctore"
WORK="$HOME/Documents/betdoctore-eval"
INV=$(find "$ROOT/data/evaluation/new-capture-inventory" -maxdepth 1 \
    -type f -name '*.combined-inventory.json' -print -quit)
test -n "$INV" || exit 1
"$WORK/.venv/bin/python" -m betdoctore.point_in_time_history \
  --inventory "$INV" --output "$ROOT/data/evaluation/score-history-cdx"
```

If `timestamp_candidates` is nonzero, a separate **opt-in** archive
body review is available. It fetches only the frozen, latest
in-window chosen captures, up to 24 response bodies by default. Large
source files (e.g. multi-megabyte CSVs) are kept locally, not in Git.
The input discovery report must have a content-addressed filename and
the referenced CDX source SHA must match. No replacement candidate is
picked after seeing a captured score.

```sh
DISC=$(find "$ROOT/data/evaluation/score-history-cdx" -maxdepth 1 \
    -type f -name '*.cdx-history-discovery.json' -print -quit)
test -n "$DISC" || exit 1
"$WORK/.venv/bin/python" -m betdoctore.point_in_time_history \
  --inventory "$INV" --output "$ROOT/data/evaluation/score-history-cdx" \
  --verify "$DISC"
```

A captured CSV must match its CDX archived-content digest. Completed
games must have paired reciprocal final-score rows; future final
scores, unpaired observations and invalid team identities fail closed.
A fixture's historical input set counts only games strictly **before**
the fixture's New York calendar date, conservatively excluding same-day
games without known completion timestamps. A technical pregame history
candidate requires at least five valid historical results for **each**
target team and 100 league games. Original scores and captures remain
private and append-only.

Even `TECHNICAL_HISTORY_CANDIDATE_RIGHTS_PENDING` does **not** mean
the model may train: this preliminary report neither establishes final
publisher source rights nor approvals of all exact game identities,
actual tipoff, or the full independent evaluation protocol. Its
`source_admitted_games=0`, `training_eligible=false`,
`periods_locked=false` and `outcomes_read_for_selection=false` are
non-overridable through this code path.

If CDX returns zero or errors, do not assume no historical source ever
existed. A Git commit timestamp is not a substitute for an independently
timestamped snapshot. Preserve the existing 7-day rule, previous
14-game metrics and draft-PR status. Require human provenance,
normalization, terms and source-identity review before a separate
source-admission and sample-freeze change.
