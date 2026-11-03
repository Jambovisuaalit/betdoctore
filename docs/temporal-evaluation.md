# Locked temporal score-only research assessment

The first new temporal assessment was completed on 2026-11-03. This is a real,
retrospective point-in-time reconstruction, not prospective blind testing or a
production model approval. Private source exports, predictions, per-game errors,
source receipts and HTML/JSON reports remain under ignored data/.

## Evidence and method locked before scoring

The source inventory contains 132 byte-verified HTML captures plus 10 previously
acquired original JSON captures within the source-season acquisition interval.
HTML JSON exports contain literal escaped JSON inside one textarea; results tables
are admitted as history evidence only when the original page explicitly proves
UTC display. Tables have no provider event ID: none is invented. Source SHA-256
always describes original bytes, never a fabricated JSON-to-HTML representation.
CDX membership and archive SHA-1 digest are checked before interpretation. Original
receipt, index and payload hashes are checked again on replay.

The retained [FixtureDownload terms](https://fixturedownload.com/terms), SHA-256
`3cc63ebadee16794c698663a400b029a4366a9d70cbf79ee4f0eee010537282c`, match the reviewed
personal noncommercial local-use scope. This does not permit public export/API
redistribution. Some archive searches failed or timed out; the saved failures are
not evidence of absent data. One selected results-page replay timed out and is
absent from the locked successful-capture inventory.

Only post-2022 captures and non-2022 test games are eligible. A March 2023 capture
with URL season label nba-2022 describes the 2022–23 season; its 2023 test games
are distinct from the December 2022 development test. Earlier scores may appear
as causal historical inputs, never as new test observations.

The plan fixed three calendar reporting strata before opening the adjudication
manifest: January–June 2023, July 2023–June 2024, and July 2024–June 2025. These
are reporting strata, not claims of full-season sample coverage. All 402
source-capacity candidates within them were frozen. There was no selection by
observed prediction errors.

Both algorithms are unchanged score-only means: the model averages each team's
last 10 observed captured full-game totals, requiring at least five observations
per team; the comparator averages the last 100 observed captured league totals.
Partial captures do not establish complete rolling team or league histories.
These are observed-data research models, not the Pace/efficiency production
model. Every used history row must be from the same NBA season, observed by T-60,
from a capture at most seven days old, and scheduled before the capture's current
New York calendar day. Conflicting histories and known pre-cutoff schedule changes
are excluded. NBA Cup finals are excluded using the versioned metadata contract.

All predictions are durably saved before reading the current result manifest.
Only then are original result-source bytes revalidated and the following frozen
exclusion rules applied identically to both models:

- Every used input must have a corroborated, consistent regular-season result
  with matching home/away scores. Inputs are never retrospectively corrected.
- Targets must pass regular identity/result checks and current-versus-archived
  schedule reconciliation. Published scheduled T-60 is used; actual tipoff is
  not asserted.

## Observed result

Of 402 frozen forecasts, 298 passed all source/data checks. 102 were excluded
because a used input referenced one of four unresolved result-quality entries;
two more failed target identity or schedule reconciliation. These exclusions were
not chosen from model errors and were not relaxed to reach 300.

| Calendar reporting stratum | Evaluated games | Actual accepted date span |
| --- | ---: | --- |
| January–June 2023 | 111 | 2023-02-01–2023-04-06 |
| July 2023–June 2024 | 39 | 2023-11-30–2023-12-12 |
| July 2024–June 2025 | 148 | 2024-11-18–2025-03-31 |

| Metric on the identical 298 games and cutoffs | Team observed-total mean | League observed-total mean |
| --- | ---: | ---: |
| MAE, points | 15.441455 | 16.607036 |
| RMSE, points | 19.491625 | 21.017067 |

The paired MAE difference (model minus comparator) is **−1.165581 points**.
The provisional 300-game planning target was not met. It is not a significance
guarantee even when met.

The prespecified primary seven-day moving-calendar-block 95% interval is
**unavailable: insufficient temporal support**. The second stratum has only a
13-day observed span, below the fixed three-block support check. Empty padding
outside the actual observed span is not used to manufacture support. The
prespecified three-day sensitivity interval is [−1.676711, −0.621742] points;
the 14-day interval is also unavailable. The favorable three-day sensitivity
result does not replace the missing primary interval or establish model validity,
representative full-season accuracy, calibration, or a betting edge. Blocks stay
within strata, with within-stratum source gaps represented by empty calendar days.

## Reproduce without changing the locked experiment

```sh
# Discovery saves original CDX responses and receipts; no target outcomes needed.
betdoctore export-discover 2022  # restricted to capture year 2023
betdoctore export-discover 2023
betdoctore export-discover 2024
betdoctore export-discover 2024 --kind results
# Acquire each successful saved discovery, retaining failures:
betdoctore export-acquire data/evaluation/embedded-exports/DISCOVERY.discovery.json --private-research
# The existing direct-feed inventory remains a separate original-byte source.
betdoctore export-capacity --feed-inventory data/evaluation/new-capture-inventory/3862cea977721f6627e98dabb4db0766d06b02a1993498ac2b1518658b9a9f3b.combined-inventory.json
# Create a lock before first scoring; never call a new lock an unseen test after exposure.
betdoctore temporal-lock data/evaluation/new-capture-inventory/3862cea977721f6627e98dabb4db0766d06b02a1993498ac2b1518658b9a9f3b.combined-inventory.json
# Exact replay of the existing assessment:
betdoctore temporal-evaluate data/evaluation/temporal-v1/8bd8086e95c55c6171db60211302ac9eaad9f0741a9c6f3fa6782711bea2c562.locked-plan.json data/regular-season/6a9e71de8d2edb51509a6d48258d5d871c00103828c3c7a45e3ae29d97d5cfc8.regular-manifest.json
```

The local prediction artifact SHA-256 is
`2e52d2df6db280e2804f46f1507f34939d40b37d1bd41058b4ce54477525f5b4`;
the evaluation report SHA-256 is
`fbe2e16b332e0e616ec5b0dbbd0a3a365d5322ffb23b9df32382cef5dec5a6da`.
Code, protocol, all acquisition receipts and the metadata contract are bound in
the lock; changing them invalidates an unchanged replay. Reports never overwrite
differing artifacts. Detailed errors and the exposure registry remain private.

The 402 frozen candidates are now exposed research data. They must not be
relabeled as a new independent test after model tuning, nor may two convenient
games be appended to repair the planning count. Data adjudication can produce an
explicitly versioned revision of this assessment; it is not a new untouched test.
Further validation needs its own locked sources/cohort and sufficient temporal
support. Advanced comparisons await admitted Pace/ORtg/DRtg evidence. Real odds,
calibration and betting-edge validation remain blocked; production is not ready.
