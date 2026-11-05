# Next independent sample: source inventory, 2026-11-05

The previous 402 frozen candidates are exposed research data. The new
`independent-capacity` command requires their exact content-addressed exposure registry
and excludes every registered game before reporting new capacity. Development-year
2022 targets are forbidden. This is an outcome-blind capacity preview, not a locked sample,
source admission, forecast, performance report or production approval.

## New acquisition

Searches retained CDX response bytes and timestamped receipts under private ignored
`data/evaluation/new-period-discovery-20261105/`:

- `view/json/nba-2025`: 57 index rows; `results/nba-2025`: 29 index rows.
- Additional `view/csv/nba-2025`, exact root `feed/json/nba-2025`, and an in-season
  feed-prefix query returned HTTP 200 empty arrays. These bounded query results do not
  prove that all possible sources are absent. An earlier wider feed-prefix request timed out.
- Post-April-2025 searches found 35 result-page and 13 HTML JSON index rows for `nba-2024`.
  The earliest listed captures in these bounded responses were after that regular season;
  they were not downloaded or admitted as pre-cutoff regular history.

Acquisition choices were saved before reading bodies: latest listed full-season 2025
JSON schedule, and all listed in-season 2025 result pages. The latter contains one Houston
capture. Both original HTML payloads passed CDX membership/SHA-1, local SHA-256, literal-only
parsing and the existing timestamp/identity checks. They were reloaded from saved receipts.

| Archived original | Archive timestamp (UTC) | Parsed content | Original HTML SHA-256 |
| --- | --- | --- | --- |
| `https://fixturedownload.com/view/json/nba-2025` | 2025-09-14 06:34:04 | 1,200 unscored schedule rows | `f8134b9d68a54cdd2c3acfb859ac667b7f65357794999b25bdcb48eae30c849f` |
| `https://fixturedownload.com/results/nba-2025/houston-rockets` | 2025-11-18 00:55:23 | 80 schedule rows, 12 scored rows | `9842e3e5fe919aec675d904ab129c642cb24643f4b24e1f47b31d81fc2b23038` |

The 1,200 rows are schedule evidence, not proof of a complete 1,230-game regular season.
The current retained FixtureDownload terms match the reviewed SHA-256
`3cc63ebadee16794c698663a400b029a4366a9d70cbf79ee4f0eee010537282c`.
Use remains private, personal and noncommercial; raw exports, receipts and per-game data
are not redistributed through Git or the API. The archive timestamp demonstrates the
captured representation's availability by that instant, not its first publication time.
A historical schedule alone does not establish historical score or advanced-stat availability.

## Proposed windows and actual blocker

Two windows are proposed for inventory, **not locked for evaluation**:

1. 2025-10-21 through 2025-12-31.
2. 2026-01-15 through 2026-04-15.

The source-capacity gate requires same-season history observed by scheduled T−60, captures
at most seven days old and at least five observed prior games for each team. The new
inventory currently provides **zero** eligible fresh-history candidates. All 1,200 schedule
candidates fail sufficient fresh two-team history; one team's 12 scores cannot supply it.
There is no qualifying 300-game sample, temporal-block support, new locked protocol, frozen
forecast set or new MAE/RMSE/paired interval. No target outcome manifest was opened by this
capacity calculation. This does not alter the earlier 298-game assessment.

The private proposed-period file is
`729ec38cb31601e21b1e2adc1c2d57470819652e76b0ff9b7ceb2a58df57fe74.proposed-periods.json`.
The private capacity report is
`b238ca0469e2d8a1d738b3b9c55f85cfa6687588fce396ae8b7b7d523166a862.independent-capacity.json`.

```sh
betdoctore independent-capacity \
  data/evaluation/new-period-discovery-20261105 \
  data/evaluation/temporal-v1/092155959d1e45a52ecf3e08c50585ebcb83e9733d67ae8544468d87728b2313.exposure-registry.json \
  data/evaluation/next-independent-sample/729ec38cb31601e21b1e2adc1c2d57470819652e76b0ff9b7ceb2a58df57fe74.proposed-periods.json
```

The command checks source receipt/original hashes and private terms; it rejects a changed
exposure registry. It reports actual observed spans per proposed period. Outer empty-day
padding cannot manufacture the primary seven-day block method's 21-day support requirement.
Even sufficient planning capacity would still require separate source/definition review,
regular identity validation and a protocol lock; the preview never approves an independent test.
300 games remain a planning goal, not a significance guarantee.

Next acquisition must supply permitted, independently timestamped, sufficiently frequent
multi-team/full-league score histories for these periods. Do not substitute current final
results, infer old receipt times, relax freshness, append convenient games or reuse the
exposed cohort. Only after source and temporal support gates pass may the protocol/cohort
be locked, both forecasts frozen before reading target outcomes, and paired MAE/RMSE with
calendar-block uncertainty evaluated. Advanced comparison and betting-edge validation remain
separately blocked.
