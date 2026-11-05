# Whole-league score-history source review — 2026-11-05

This follow-up found two retrievable historical Kaggle file versions with all 30 current
NBA teams represented in the 2025–26 regular-ID-prefix candidates. Both are retained in
private quarantine. **No rows have been admitted to point-in-time features or a new test.**
The existing zero-capacity report describes the previously verified FixtureDownload inventory;
it does not imply that no other historical dataset exists.

## Publisher and version evidence

The [publisher page](https://www.kaggle.com/datasets/eoinamoore/historical-nba-data-and-player-box-scores)
currently labels the dataset CC0 and credits NBA.com for the underlying data. That observed
publisher label is recorded separately from upstream rights/lineage approval. The review does
not certify that all underlying rights or the intended-use conditions have been resolved.
Only basic Games.csv pilots were retrieved, not player, play-by-play or advanced statistics.

The public [Kaggle file-list API](https://www.kaggle.com/api/v1/datasets/list/eoinamoore/historical-nba-data-and-player-box-scores?datasetVersionNumber=300&pageSize=20)
returned version-specific Games.csv metadata. Versions 260, 280, 300, 320, 340, 360, 380, 400
and 420 have listed file creation dates spanning 2025-11-02 through 2026-03-25. These are
**provider-reported file creation dates**, not independently established public publication times.
The [official client](https://github.com/Kaggle/kaggle-api/blob/main/src/kaggle/api/kaggle_api_extended.py)
supports explicit dataset version numbers for file listing and download.

An important API distinction was verified: the dataset `view` response still described current
version 538 when passed `datasetVersionNumber=300`. It must not be used as proof that a selected
historical version was returned. The version-specific file listing and downloaded size were
checked separately. No current file was relabeled as an older capture.

Acquisition plans were saved before opening each pilot's score bytes. Original file bytes,
SHA-256, request parameters, metadata responses and receipt hashes remain under ignored
`data/evaluation/multiteam-history-search-20261105/`. Temporary signed redirect URLs were not
logged in the receipts. The publisher page retained through Firecrawl is a provider-returned
representation; it is not asserted to be original HTTP wire bytes or an old archive capture.

| Pilot | Listed Games.csv creation time (UTC) | Bytes | CSV rows, all eras/types | Last raw game date | Current-season 002-prefix candidates |
| --- | --- | ---: | ---: | --- | ---: |
| 300 | 2025-12-11 08:04:51.958 | 10,019,407 | 72,311 | 2025-12-10 | 361 |
| 400 | 2026-03-05 08:12:35.324 | 9,656,082 | 72,884 | 2026-03-04 | 926 |

CSV SHA-256:

- Version 300: `9597f55bcd0cbbbe0463dadb814ded7526aa6d63aaa4b3d177957bdedb75c247`.
- Version 400: `bde7c6864b3dd8950fb45ac599f5b39ab8e7af137e2612ba37b73f1070ef024b`.

Candidate counts use raw game-ID prefix 002 and dates from 2025-10-21 through 2026-04-15.
They are not verified regular-season coverage, eligible forecast counts or independent tests.
The 361 common IDs are counted once when discussing overlap, not added to 926.
Structural checks found no duplicate candidate IDs, invalid positive integer final scores,
tied final scores, unknown current team names or identical opponents in the selected rows.
They do not independently verify that the reported scores are correct.

## Revision and definition findings

The two pilots share 361 candidate game IDs. All earlier IDs remain in the later version,
but **one score pair changes** and **135 raw date-time values change**, each by +5 hours.
Home/away canonical team identities do not change. No correction was applied automatically.
The score revision remains a private source-quality item requiring adjudication before any
claim that the two versions are consistent.

The schema changes from 17 to 22 columns. In version 300, the gameType field mixes blank,
`in-season` and other labels; the later file uses labels such as Regular Season, All-Star
Game and Emirates NBA Cup. The field name gameDateTimeEst alone is insufficient to explain
the five-hour shifts. Neither the time-zone contract nor the phase mapping is approved.
Do not silently apply a five-hour adjustment, use later values as earlier observations,
or merge both schemas under an assumed common definition.

The private structural audit is
`dc80a8e0f84fad2e0babf903f7a745e928b616c864838e6c5eb64c329d274631.pilot-structural-audit.json`.
The retained offline auditor is
`80e4372ebc7222fb2d7db93e5d0885fdec1f035db82732d1eb1032b7d0ed615a.pilot-auditor.py`.
It rechecks receipt, metadata, CSV hashes and sizes before counting rows and comparing versions.
Detailed changed rows and source-row numbers stay private.

## Other sources checked

- Both active Neil Paine CSV filenames and raw/GitHub URL variants were investigated.
  Four bounded exact-URL CDX queries for 2025-10-14 through 2026-04-15 returned HTTP 200
  empty arrays. These queries are not proof of global absence. Git commit dates remain
  insufficient historical-publication evidence.
- [SportsDataverse schedule release metadata](https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_nba_schedules)
  and [team-box-score release metadata](https://api.github.com/repos/sportsdataverse/sportsdataverse-data/releases/tags/espn_nba_team_boxscores)
  show releases originally published in March 2023, but their listed season-2025/2026 assets
  were created after the proposed test windows. The 2026 CSV assets inspected were created
  in September 2026. The old release date cannot certify these newer bytes' historical availability.
  Data licensing/lineage is also separate from the repository's software license.
- The Kaggle dataset-page prefix CDX lookup timed out. Its status is unknown, not zero.
  No independent archive body was admitted from that lookup.

## Remaining admission gates

1. Establish a permitted source-use/lineage decision with retained supporting evidence.
2. Bind the exact historical version bytes to public availability before each T−60 cutoff.
   File creation dates, current access, old release dates and Git dates are insufficient alone.
3. Resolve the time-zone/schema/phase definitions and the observed score revision while
   preserving both original versions and their actual availability evidence.
4. Acquire adequately frequent, verified snapshots across both proposed periods, then assess
   fresh two-team history and actual temporal support. Two whole-season snapshots are not
   by themselves a qualifying 300-game forecast sample.
5. Only after those gates pass, freeze a new protocol/cohort excluding 2022 and the exposed
   402 games, freeze both models' forecasts, and then open the target outcome manifest.

No new MAE, RMSE or uncertainty interval was calculated. No advanced feature rows, production
approval or betting-edge validation resulted from this source review.
