# Acceptance ledger

## 2026-10-27 — technical basic-result foundation

The user accepted the preceding phase as the **technical foundation for result data**.
This covers the basic-result schema, source snapshots, idempotent local ingestion,
private non-commercial source isolation and the existing integrity/quarantine workflow.

The next acceptance boundary is season coverage and historical availability before joining
Pace, Offensive Rating or Defensive Rating datasets. Technical-foundation acceptance does
not assert complete season coverage, resolve quarantined records, certify historical
publication/receipt timestamps, validate advanced datasets or change production readiness.

See [the season and availability audit](season-availability.md) for that separate gate.

## 2026-10-27 — parallel V1 regular work and advanced staging

The user authorized regular-season completion and advanced-statistics staging in parallel,
with playoff completion in a separate queue. V1 readiness is therefore scoped to each explicitly
selected regular cohort; global playoff or unrelated-season incompleteness does not block it.
Each evaluated target still needs clean result/identity evidence and causal published inputs.
Staging is infrastructure, not approval to join unverified advanced rows into features.

The next business milestone is the first real reproducible regular-season forecasting assessment.
The score-only protocol in [regular-evaluation.md](regular-evaluation.md) provides the initial
limited-cohort assessment while advanced source ingestion/normalization/timing remain separate.
This is not production approval, proof of forecast improvement or a betting-profitability result.

## Next independent evaluation acceptance contract

The 2022 score-only cohort is development evidence and cannot be reused as a new
independent test. The next sample requires its own timestamped captures and
predeclared separate periods. The provisional target is >=300 games from >=2
periods, without a significance guarantee. Both models share games and cutoff;
report paired MAE difference and temporal block uncertainty. Advanced rows must
pass source, definition and availability checks before comparison. Separate model
and betting-edge validation is mandatory before production approval. See
[independent-evaluation.md](independent-evaluation.md). New sample admission is
BLOCKED pending verified new captures and a frozen period inventory.
