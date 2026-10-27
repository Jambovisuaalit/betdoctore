# Advanced-statistics staging

This is an isolated intake/review path for Pace, Offensive Rating and Defensive Rating.
No real advanced dataset is bundled, acquired, joined into features or used by this phase.
All new software-test metric values and publisher records are explicitly synthetic.
Missing playoff data does not block an explicitly curated regular-season subset.

## Storage and contracts

Migration `0003` adds `advanced_stage_batches` and `advanced_stage_rows`, separate from
basic-result observations, `source_records`, feature snapshots and model artifacts.
Application writes are append-only: identical re-imports are idempotent; conflicting reuse
of a batch/row identity fails instead of overwriting. The row-to-batch foreign key preserves
provenance. Database administrators still control privileged manual database writes.

`AdvancedSourceManifest` records the source URL/version, normalization version, optional reviewed selection-manifest hash, SHA-256, actual acquisition time,
authorization reference, research authorization, private/non-commercial or redistributable
scope, and whether the entire source is synthetic. It also carries per-metric calculation
version, units, possession convention, overtime convention and aggregation definition.
The default normalization version is `unreviewed` and blocks eligibility. A reviewed selection
manifest creates a distinct curated batch without changing the vendor source version or rewriting
the original full staging batch. The manifest does not itself establish an external source's rights or normalization fidelity.

`AdvancedObservation` retains provider game/team/row IDs, mapped internal game/team IDs,
season and phase, per-game/rolling/season scope, effective-period start/end, provider publication,
source observation, actual receipt, source revision, superseded content digest and metrics.
Missing mappings, incomplete metric bundles, unknown units/conventions, unsupported aggregation,
unverified effective periods and non-regular phases are retained for quarantine/review.
Naive times, nonfinite values, impossible publication/receipt order and invalid numeric ranges
are invalid observation contracts. Invalid rows are stored as quarantined raw JSON representations;
nonfinite values use an explicit `invalid_nonfinite_float` marker, never an invented numeric value.

Supported V1 review conventions are a per-game bundle of all three metrics, pace in possessions
per 48 minutes and ratings in points per 100 possessions. Overtime convention must be known and
consistent. These requirements do not derive possessions or ratings from final scores.

## Intake API

```python
with Session(engine) as session:
    with session.begin():
        report = stage_batch(session, manifest, normalized_rows, source_bytes=original_bytes)
```

The actual source bytes must match the manifest SHA-256. Omit `source_bytes` only to retain an
unverified batch in quarantine. A mismatched digest aborts before batch insertion. A different
snapshot-verification context produces a distinct batch; prior observations remain unchanged.
Snapshot verification does not prove that a normalized row was correctly parsed from those bytes.
Source-specific adapters and explicit normalization review are separate acceptance work.

Possible stored statuses are `QUARANTINED` and `STAGED_NOT_PROMOTED`. Neither status is a
production promotion. Each report includes `promoted: 0` and `production_features_written: false`.
Callers should let transaction errors roll back the whole intake operation.

## Cutoff and subset review

`assess_for_cutoff` verifies one observation for a caller-supplied curated regular-season
identity and a verified prediction tipoff. The cutoff must be exactly tipoff minus 60 minutes.
The observation's effective period, source observation/publication if provided, actual receipt
and source acquisition must precede or equal cutoff. Synthetic inputs are rejected from a real
evaluation. Private-only inputs are rejected from a commercial evaluation scope.

`readiness_report` reviews a batch against an explicit `regular_game_keys` subset. It excludes
unselected playoff and other staging rows from that subset's gate; it does not require a complete
historical league database. Every selected game must have exactly one observation for each of its
two teams, with complete metric bundles. Missing selected games and unresolved multiple revisions
block review. Source-byte verification and explicit normalization review are required independently.

A successful review says `READY_FOR_EXPLICIT_CURATED_REVIEW`, not production-ready, and never
writes into feature tables. A regular-season scope or normalized source mapping must not be marked
verified merely because values fit the schema. Source-specific acceptance evidence is required.

## Historical availability and revision policy

Provider publication labels and `historical_timing_claim_reference` can be retained, but this
module has no advanced-data historical timing verifier. They cannot override local receipt or
backdate eligibility. A final-score archive capture proves no Pace/ORTG/DRTG value's availability.
A historical cutoff before actual acquisition/receipt remains blocked with
`HISTORICAL_ADVANCED_AVAILABILITY_NOT_VERIFIED` until an appropriate verifier is implemented.

Corrections use a new source row identity/revision and optional `supersedes_content_digest`.
The predecessor must exist for the same source, game and team. Earlier versions stay present;
no helper silently chooses the latest revision. Multiple versions in a selected game/team bundle
remain blocked until an explicit reviewed version selection is represented by a curated batch.
