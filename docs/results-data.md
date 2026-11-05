# Basic result foundation: 2021–2026

Scope: NBA final scores and source-supplied metadata for calendar dates 2021-01-01 through
2026-10-27, not a claim that the unfinished 2026 calendar year is complete. The user confirmed
private, non-commercial research on 2026-10-27. Advanced statistics remain locked.

## Sources and permission boundaries

- **Neil Paine NBA Elo archive:** pinned Git commit
  `9a485bacef9f18f6a8e3ec671f13b9609386f0fa`, file `NBA Elo 2025 - nba_elo.csv`.
  Explicit MIT notice: copyright (c) 2024 Neil Paine. Original FiveThirtyEight data attribution
  and CC BY 4.0 notice retained. Extracts scores/calendar metadata only, not Elo/RAPTOR or forecasts.
  Source: https://github.com/Neil-Paine-1/NBA-elo ; original data license:
  https://github.com/fivethirtyeight/data/blob/master/LICENSE .
- **FixtureDownload NBA 2020/21–2026/27:** personal, non-commercial local research only, based on
  https://fixturedownload.com/terms . No raw data, detailed reconciliation, or downloadable source
  files are published in GitHub or exposed by the read-only results API. The user's scope does not
  grant commercial rights. Reassess permissions before changing the deployment/use case.
- Kaggle's NBA.com-derived CC0 dataset was not imported: its upstream rights remain unresolved.
  No NBA.com endpoints were scraped. FiveThirtyEight's old live CSV URL now redirects to an
  unrelated HTML page; arbitrary HTML is never accepted as a dataset.

These are recorded source grants and usage boundaries, not a guarantee about rights a publisher
does not own. Different publishers do not prove independent upstream collection.

## Reproduce the local acquisition

```sh
alembic upgrade head
betdoctore results-acquire
betdoctore results-import --start 2021-01-01 --end 2026-10-27
# This flag records the permitted private scope, not commercial access:
betdoctore private-results-import --private-research --start 2021-01-01 --end 2026-10-27
betdoctore results-reconcile --start 2021-01-01 --end 2026-10-27
```

All raw exports, original terms, source manifests, normalized private records and detailed
JSON/HTML reconciliation reports live under ignored `data/results/`. Database observations live
in `result_source_snapshots` and `basic_results`, separate from the engine's possession-based
`source_records`. Repeat imports of the same bundle are idempotent. Conflicting immutable rows
or source identities fail. Never overwrite a saved snapshot when refreshing an export: acquire
into a new directory and explicitly reconcile source revisions.

The pinned archive verifies the exact CSV and license hashes. Mutable FixtureDownload exports
record byte hashes, actual acquisition times, source URLs, source season and local terms hashes.
The pipeline stops if the personal-use grant wording changes. Existing bundles are verified,
not fetched again silently. Keep local bundles and database backups together; GitHub alone does
not contain the private dataset. A newly fetched mutable export can legitimately differ.

## Integrity checks and limitations

1. **Source integrity:** HTTPS retrieval, saved original bytes, SHA-256 and recorded licenses/terms.
2. **Internal integrity:** opposing archive rows must agree on identities, scores, season and
   playoff/neutral flags. Exactly two rows collapse to one game. Duplicate game/match identities,
   unknown teams, invalid/tied scores, partial scores and future scored fixtures fail closed.
3. **Metadata integrity:** names map to canonical NBA IDs. Missing home designation, neutral-site
   status, actual tipoff, completion and publication times remain null. A scheduled timestamp is
   never relabeled as actual tipoff. Source venue labels are not independently historically verified.
4. **Cross-source audit:** exact game identity and scores must agree; conflicts and possible
   date disagreements are quarantined from the working view. No automatic majority vote, typo
   correction, or date shifting. Single-source observations remain explicitly unverified.
5. **Coverage integrity:** presence of all six years or a plausible game count does not prove
   completeness. FixtureDownload primarily provides regular-season schedules and cup fixtures;
   its exports do not establish complete playoff/play-in coverage. The archive stops 2025-04-13.
   Later postseason gaps and source freshness require a separate expected-game manifest.

Archive calendar dates carry unknown timezone provenance. FixtureDownload explicitly labels
scheduled timestamps UTC; the adapter records the timestamp and derives a comparison calendar
date in America/New_York. Both date bases remain labeled. Tipoff changes and publication histories
are unknown: `available_at` is the acquisition time, never a fabricated historical time.

The `/results` endpoint paginates only the redistributable archive source and labels integrity as
structural-only. Private source observations are excluded by source whitelist. The private
combined working view exists only in local reconciliation reports; it is not a training input.

## Acceptance gate

`ADVANCED_STATS_UNLOCKED` is false. To unlock a later milestone, resolve score/home/date conflicts
using traceable authorized evidence; obtain complete expected-game manifests including postseason
and play-in; review single-source coverage; verify historical timestamps and source independence;
then rerun reproducible integrity checks. No possessions, pace, offensive/defensive ratings, model
fit or real-data betting backtest was generated in this phase.

See `docs/evidence/results-2021-2026-audit.json` for the redistributable archive's actual local
import evidence. Detailed private-source findings and disputed scores remain under `data/`.

## Subsequent V1 scope decision

The user authorized a clean selected regular-season cohort to advance independently of the
postseason backlog. The original whole-history gate is retained as an audit finding, while
[regular-season.md](regular-season.md), [advanced-staging.md](advanced-staging.md) and
[regular-evaluation.md](regular-evaluation.md) define the newer per-cohort boundaries.
No unresolved row or unsupported historical metric is admitted merely because playoffs are
nonblocking for V1.
