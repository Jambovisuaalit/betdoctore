# First real regular-season forecasting assessment

V1 can evaluate an explicit conflict-free research regular-season cohort while playoff completion and advanced
staging proceed independently. This assessment is a **score-history baseline**, not a claim that
Pace/Offensive Rating/Defensive Rating values were joined or historically certified.

## Frozen protocol

The packaged `resources/regular-evaluation-protocol.json` fixes the source versions, model,
benchmark, training windows, minimum history and seven-day maximum history-capture age.
The schedule cohort is selected from all five known NBA-2022 team-schedule captures on
2022-12-06 (Atlanta, Denver, Minnesota, New York and Utah). Selection is based on the available
archives, not on which games the model predicts well. This is an archive-availability-selected
sample, not a representative full-league or prospective untouched holdout.

- History: exact FiveThirtyEight CSV content captured 2022-12-06T22:42:08Z, verified against
  Internet Archive CDX and its pinned SHA-256. Only season-2023 completed regular-game scores
  are used; Elo, RAPTOR, forecast fields and advanced metrics are ignored.
- Targets: originally unscored future games in checksum-verified contemporaneous schedule
  captures. The cutoff is 60 minutes before the **published archived scheduled time**. Actual
  tipoff is not asserted. Information from a later schedule capture cannot revise an earlier
  frozen prediction; conflicting schedules already published before cutoff cause exclusion.
- Model: average of the two teams' mean full-game totals in their last ten available regular
  games, with at least five per team. Scores include overtime as observed.
- Benchmark: mean full-game total of the last 100 available league regular games.
- Time: every history value must be public by cutoff; capture age is capped at seven days.
  The input history remains frozen when no later verified capture is available. This is
  disclosed explicitly rather than pretending to receive daily feeds in 2022.

Forecast generation has no outcome-manifest parameter. It writes an immutable, content-addressed
prediction artifact before the runner reads current outcomes. Protocol, source-body, acquisition
receipt and evaluator-source hashes are retained. The separate scoring stage requires each target
to pass the regular result gate, have corroborating publisher outcomes and reconcile the archived
schedule/home identity against the saved current result catalog. Every exclusion is reported.
Original saved outcome-source bytes are revalidated for the selected targets after prediction freeze; an edited normalized outcome cannot silently become ground truth. Unrelated season gaps, incomplete playoffs and unselected staging rows are not cohort blockers.

## Reproduce privately

```sh
alembic upgrade head
betdoctore regular-manifest
# Use the printed manifest path below.
betdoctore regular-evaluation-acquire --private-research
betdoctore regular-evaluate data/regular-season/MANIFEST.regular-manifest.json
# Repeating with identical bundles produces the same prediction/report hashes.
```

Inputs, original private schedule captures, detailed forecasts and HTML/JSON evaluation reports
stay under ignored `data/evaluation/`. The source's personal non-commercial restrictions remain
in force; there is no public results/forecast endpoint for this private assessment. No wagering
execution is introduced.

## Interpretation and next acceptance boundary

The report supplies MAE, RMSE, mean error, exact sample size, cohort membership, benchmark results,
source/code/protocol hashes and all exclusions. A real calculation can show a worse MAE than the
benchmark; it must not be retuned or relabeled as profitable on that basis. A small initial sample
is software/data-path evidence and a forecasting baseline, not demonstrated generalization.
There are no invented odds, Over/Under calibration scores, ROI or profitability metrics.

Next: expand independently verified pregame schedule/history coverage, preserve protocol versions,
use a chronologically separated larger evaluation cohort, and compare approved advanced features
against this baseline only when their own row/version/timing gates pass. Historical score capture
evidence is never reused as proof of advanced-metric availability.

The independent-reference licensing/lineage review workflow remains intact. Cross-publisher
result consistency in this research assessment does not set its human review flag or certify
independent original collection, and does not approve production training or advanced promotion.
