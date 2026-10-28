# Zhao et al. 2023: opponent-adjusted NBA totals research hypothesis

**Decision**: use the paper as an architecture/feature-selection hypothesis, not
an independently validated pregame totals predictor. The paper predicts the **winner**,
not the **full-game total**. Its reported mean classification accuracy of 71.54%
for GCN + random-forest-selected features is not a BetDoctore MAE, calibration
result, or betting edge. Reference: Zhao, Du & Tan, *Entropy* 25(5), 765 (2023),
DOI: https://doi.org/10.3390/e25050765, especially Tables 3, 5, 6 and 9.

## Major as-of leakage concern

The paper describes 44 features calculated from team statistics of the
**game being classified**, including game-level EDiff, ORtg, DRtg, shooting
percentages and possessions. It also describes random 70/10/20 data splits
and graph neighbors connecting preceding **and subsequent** games.
Publication alone is insufficient to establish leakage-free pregame
prediction. Its 71.54% must not be reproduced as a T-minus-60 estimate
without inspecting the original implementation and independently
rebuilding its temporal boundaries.

The RF importance values in the paper are for **winner classification**;
they are not weights or rank ordering to copy into NBA Over/Under.
In particular, a low feature importance for Pace in that paper does
not establish Pace's relevance for predicting full-game points.

## Frozen staged experiment order

The machine-readable, explicitly *blocked* research draft is
`resources/opponent-adjusted-research-protocol.json`:

| Candidate | Purpose | Evidence requirement |
| --- | --- | --- |
| m0: league last-100 mean | Already defined baseline | Verified historical score captures |
| m1: team last-10 mean | Existing baseline | Same source/time gate |
| m2: opponent-adjusted regularized linear totals regression | First hypothesis | T-60 verified **past-game** scores and opponent history |
| m3: opponent-adjusted RF totals regression | Competing hypothesis | Exact same past-game inputs and frozen cohort |
| m4: temporal GCN regressor | **DEFERRED**, separate ablation | Separate advanced availability gate and causal graph |

Opponent-adjusted scoring means **past** points for/against should be
interpreted relative to the past opponents' historical strengths as
observable by the target-game cutoff. This is *not* ORtg/DRtg unless
possessions are available and normalization reviewed. Candidate input
features may include past points for/against, schedule/rest, home
indicator and opponent-adjusted historical scoring. Neither outcome of
the target game nor future game edges may enter features, graph topology
or learned preprocessing.

Only after source admission: consider a deterministic regularized linear
estimator first, and a modest RF trained solely on preceding windows.
Preprocessing, normalization, opponent baselines, random-forest feature
selection, all graph messages and tuning must be fitted **inside**
each chronological training fold; no shuffling across future target
games or feature-ranking over the holdout. Include explicit cold starts
and observation failures as exclusions.

Evaluate all candidates on exactly the same target games and *published*
schedule T−60 cutoffs; never silently intersect result sets. Forecast
artifacts must be hash-frozen before opening future outcomes. Keep
two or more distinct post-development periods, planning target >=300
games (not a power guarantee), fixed seven-day age cap, and the paired
MAE difference with RMSE/mean error/per-period breakdown and
3/7/14-day block-bootstrap sensitivity. An outcome-selected change
to the sample, capture age or model tuning invalidates independence.
The 14-game December 2022 cohort remains exploratory, not the new
holdout.

## State and hard gates as of this document

The 18 historically archived schedule captures contain 363 future
unscored candidates, but **zero new admitted games** currently pass
the required compatible score-history freshness verification.
The Neil Paine Git commit inventory supplies metadata discovery leads
only, not verified public score availability. The independent source
lineage/rights review, 2025–26 second source, and historical Pace/ORtg/
DRtg availability remain separate, blocked requirements.

`python -c 'from betdoctore.opponent_research import *; print(validate_hypothesis_protocol(read_hypothesis_protocol()))'`
checks research-design consistency only. It **never trains** an RF,
linear model or GCN; does not ingest/sanitize private publisher data,
does not auto-admit an input, does not unlock a training or
production gate, and does not rewrite existing baseline results.
Any future model implementation requires explicit, eligible
point-in-time data and a separately frozen evaluation run.
