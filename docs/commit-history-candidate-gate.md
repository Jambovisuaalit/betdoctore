# Git-commit score-history discovery candidate gate

The 18 verified archived 2023–25 schedule captures produced 363
outcome-blind future unscored fixtures, but the first six checked
public-score-history captures were **not** within seven days of any T−60
candidate cutoff. Never relax the seven-day window after seeing results.

A **new discovery lead** is the public `Neil-Paine-1/NBA-elo` repository.
Its `nba_elo.csv` path has numerous commits with **self-reported Git
committer dates** spanning February–June 2024 and November 2024–March
2025. This overlaps candidate seasons and is useful for *targeting*
independent archived capture searches. It does **not** prove the file
was on GitHub, or its scores were publicly available, at that commit date:
Git authors can set both author and committer dates, and an unsigned commit
hash proves bytes/metadata integrity, not first publication. Git timestamps
are **not** admissible T−60 evidence by themselves.

Run in a clean checkout of PR #2 on the Mac. This needs only **public GitHub
commit metadata**, not an NBA score download or betting-odds access:

```sh
ROOT="$HOME/Documents/betdoctore"
WORK="$HOME/Documents/betdoctore-eval"
"$WORK/.venv/bin/python" -m betdoctore.commit_history_inventory \
  --inventory "$ROOT/data/evaluation/new-capture-inventory/3862cea977721f6627e98dabb4db0766d06b02a1993498ac2b1518658b9a9f3b.combined-inventory.json" \
  --output "$ROOT/data/evaluation/commit-history-candidates" --discover
```

The inventory path is illustrative: verify the actual basename from the
`capture-inventory` output; the input must be content-addressed. If
the report hash points to a different file, locate the correct
`*.combined-inventory.json` under that directory.

Re-run without network by passing a generated digest-named
`*.commits.json` file with `--commits` instead of `--discover`.

The output only reports which T−60 dates are within seven days of
a candidate **self-declared** commit time, without reading game outcomes.
All matches remain `COMMIT_DATE_CANDIDATE_UNVERIFIED`,
`source_admitted_games=0`, `periods_locked=false`, and
`training_eligible=false`.

Next: independently verify source publication availability by cutoff
(e.g. a timestamped third-party Internet Archive copy of the exact blob,
not just its repository commit time), the actual per-game historical
score content, license/lineage and team histories, and the regular-season
identity gates. Only after that may an authorized frozen sample be
constructed **before** reading its target outcomes. New advanced
features require a separate, independent timing and normalization audit.
No changes to previous 14-game experiment, production or PR Draft state.
