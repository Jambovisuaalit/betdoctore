# Season coverage and historical availability

The technical result foundation was accepted by the user on 2026-10-27. This phase audits
completed seasons ending 2021–2026; ongoing 2026–27 is reported separately. It does not
attach Pace, Offensive Rating or Defensive Rating data or alter accepted source observations.

## Reproduce

Keep the existing authorized local source bundles under `data/results/`:

```sh
betdoctore availability-acquire --source fivethirtyeight
betdoctore availability-acquire --source fivethirtyeight-latest
betdoctore availability-acquire --source neil-paine
betdoctore foundation-audit --as-of 2026-10-27
```

Acquisition uses Internet Archive CDX and identity-mode replay for three fixed, approved
original CSV URLs. CDX responses and acquisition receipts are saved independently.
Each payload must match the archive's SHA-1 content identifier and receives a local SHA-256.
Origin, MIME type, timestamp range, schema and matching CDX membership are checked. HTML,
unlisted captures, changed payloads, contradictory scores within a capture and scored future
games are rejected. Blank future schedule rows never become result-availability evidence.

The JSON/HTML report, original captures and detailed private-source comparisons stay under
ignored `data/`. Archive raw CSVs may include other original publisher fields; this workflow
extracts only participant IDs, calendar dates and final scores. Advanced features are not imported.

## Season coverage is separate from calendar-year coverage

The original imported scope began 2021-01-01. The audit reads the saved source bytes from
2020-12-01 to examine the full 2020–21 season boundary. It reports boundary games without
inserting or overwriting database rows. This distinguishes an import-window omission from
a game actually absent from the source.

The packaged `resources/season-contract.json` records reviewed format and playoff-series
metadata with primary-source links and document hashes. It expects:

- 72 regular-season games per team in 2020–21: 1,080 distinct league games.
- 82 regular-season games per team in the following completed seasons: 1,230 league games.
- Six play-in games separately; non-playoff leftovers are not silently labeled play-in.
- NBA Cup championship games separately, outside the regular-season totals. Cup group,
  quarterfinal and semifinal games are not added again as extra regular-season games.
- Completed playoff series counts checked by participant pair, not only league total.

Source format references:
https://www.nba.com/news/nba-announces-structure-and-format-for-2020-21-season and
https://www.nba.com/news/nba-cup-101 . Completed bracket references for 2022–2026 are
`https://www.nba.com/playoffs/{year}`. The legacy 2021 bracket does not expose all series
in its current representation; the four linked round-schedule articles supply its series
metadata. Document representations are retained locally; full articles are not republished.

Regular-season checks compare expected identity sets from the saved fixture source, per-team
balance, observations from the other archive source and usable identities after quarantine.
A fixture source cannot independently certify its own coverage. `SOURCE_MANIFEST_MATCH` means
the current source-manifest comparison passed, not an independent complete-history certificate.
A matching playoff series count likewise does not prove every exact event identity/date.
Missing playoff/play-in observations, unexplained non-regular keys and result conflicts remain
explicit blockers. Ongoing-season unscored past fixtures are reported without inventing final
scores or assuming that a scheduled start proves completion.

## What historical availability evidence means

Three times must remain distinct:

1. **First publication:** when the original provider first exposed that exact value. Unknown
   unless independently evidenced; a game date or expected game duration is not a substitute.
2. **Public available-by:** an exact matching value was present in a checksum-verified public
   archive capture at its capture timestamp. This establishes an upper bound on when it was
   already public, not the first publication time.
3. **Local receipt:** when BetDoctore actually downloaded its source snapshot. Current local
   `retrieved_at` and `available_at` remain unchanged; public historical capture evidence never
   rewrites local ingestion into the past.

Evidence binds to a semantic fingerprint of the game key and exact final-score pair.
A revised or conflicting score cannot inherit an earlier different value's capture time.
The score-only as-of predicate checks the exact aware cutoff, including the one-second boundary.
This predicate is not authorization to train with unverified schedule metadata or quarantined rows.

Publisher Git commit dates are retained only as context: they do not prove when a commit was
pushed publicly, when a row was first published, or when this system received it. File headers,
HTTP Last-Modified and guesses such as game date plus three hours are not substituted for evidence.
The CDX search is bounded to the configured originals/time ranges and monthly capture selection;
no returned capture is not proof that no historical copy or publication ever existed elsewhere.

## Gate

The report separates technical-foundation acceptance, season completeness, score-content timing,
historical schedule versions and advanced-data timing. Public score capture evidence alone does
not verify actual tipoff, historical schedule changes, first publication, result completion or any
Pace/ORTG/DRTG value. No model performance or real-data profitability is computed here.

`ADVANCED_STATS_UNLOCKED` remains false until exact phase/event coverage, missing results,
quarantine resolution and the relevant field-level availability evidence are reviewed and pass.
The advanced source must additionally provide its own version/publication history; availability
of a final score never proves availability of subsequently corrected efficiency statistics.

## V1 dependency update — 2026-10-27

The user subsequently authorized cohort-scoped regular evaluation and advanced staging in parallel.
This global full-history audit remains diagnostic. Its unresolved playoff rows do not veto an
individually verified V1 regular cohort. The [regular manifest](regular-season.md) owns separate
quality/history/postseason queues; the [evaluation protocol](regular-evaluation.md) independently
verifies its historical fixture and score inputs. Advanced staging remains isolated from features.
