# New temporally separated regular-season evaluation

The December 2022 assessment is development/exploratory evidence. It is not a
new independent holdout and must not be relabeled as one. No new sample has yet
passed capture admission. The packaged independent-evaluation-plan.json is a
draft, with no selected periods; it does not assert 300 available games.

Before reviewing new outcomes, freeze the model versions, baseline, two or more
nonoverlapping evaluation periods, capture inventory and analysis settings.
The planning target is at least 300 games across at least two separate periods.
This is not a statistical power calculation or a significance guarantee.
New periods require their own timestamped source captures, original bytes,
checksums and historical availability verification. A hash or an operator's
assertion alone is not proof that information was available at T-60.

Both forecasts must use exactly the same games, actual totals and timezone-aware
cutoff instants. No silent cohort intersection is allowed. Historical admission
must additionally verify that the cutoff is scheduled tipoff minus 60 minutes
and that every input was available then. The analysis command does not perform
that source admission and always reports independent_test_ready=false.

`betdoctore paired-evaluate MODEL.json BASELINE.json PERIODS.json` accepts arrays.
Each forecast row contains game_key, date (ISO calendar date), cutoff (aware ISO
instant), prediction and actual. Period rows contain inclusive start/end dates.
Keep inputs and resulting output under ignored data/. Save stdout to a local
JSON report. Input outcome dates in calendar year 2022 are rejected.

The estimand is the mean paired absolute-error difference:
abs(model-actual) minus abs(baseline-actual); positive values favor the baseline.
The exploratory 95% percentile interval resamples consecutive calendar-day
blocks within each period. All games within a day stay together, empty days
inside the observed span remain represented, and blocks never cross periods.
Original period game-count weights remain fixed. Default settings are 7-day
blocks, 2000 replicates and seed 20261027; report sensitivity at 3 and 14 days
without selecting a favorable interval. Each period needs at least three blocks
of observed calendar span; otherwise the interval is unavailable. Empty sampled
replicates also invalidate the interval. Block length and effective temporal
support still need review; this procedure is not a guarantee of coverage.

Advanced comparisons require source authorization/provenance, reviewed metric
definitions, historical availability, T-60 eligibility and both-team coverage.
Use the existing advanced staging/readiness checks. Staged rows are not approved
features, and this analysis utility cannot promote them. No actual advanced
comparison is currently admitted.

Production approval remains blocked pending separate model validation and
betting-edge validation using real historical odds, settlement and calibration.
Neither sample size nor a confidence interval automatically opens these gates.

Method background: [Künsch (1989), The Jackknife and the Bootstrap for General
Stationary Observations](https://doi.org/10.1214/aos/1176347265). The particular
calendar-day stratification and support checks above are engineering choices,
not a claim that this finite sample satisfies the paper's asymptotic conditions.
CLI reports include hashes of all three input files and the evaluator source.
