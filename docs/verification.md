# Verification evidence — 2026-10-27

## Local checks

- Editable package installation: passed on Python 3.12.14.
- Dependency integrity (`pip check`): passed.
- Ruff static analysis: passed.
- Pytest: 25 passed. One upstream Starlette/httpx deprecation warning.
- SQLite migration upgrade, schema drift check, downgrade and re-upgrade: passed.
- PostgreSQL offline migration SQL generation: passed; this is not a PostgreSQL execution test.
- Synthetic CLI end-to-end backtest: passed, HTML/JSON created in `reports/fixture`.
- API TestClient health, read-only method rejection, database readiness, persisted snapshots and
  model/odds analysis: passed.
- Delayed statistics, future outcomes/odds/models, exact-line pairing, push probability, EV/Kelly,
  win/loss/push settlement, overlapping stake reservation and model reproducibility: tested.
- CSV and Parquet round trips and historical-feed mocked responses: passed.
- Bytecode compilation and wheel packaging: passed.
- Additional 80-game synthetic refitting run: 25 predictions, 25 model versions and 25 research
  betting decisions completed. This is integration coverage, not performance evidence.

No live odds calls were made. The adapter was tested with an explicitly synthetic mocked response.
Fixture metrics are only synthetic software evidence, and are intentionally not promoted as
historical accuracy or profitability. ROI is null for the default uncalibrated PASS-only fixture.

## External checks

PostgreSQL CI passed installation, Ruff, migrations, tests and fixture reporting on the original
platform commit `dec98b5`: https://github.com/Jambovisuaalit/betdoctore/actions/runs/40461128217.
Subsequent fixes and the Compose build/API smoke check run on the PR's current head; inspect
those checks for the final runtime result.

Docker and PostgreSQL server binaries are unavailable in this local environment. Live PostgreSQL
migrations and integration tests are configured in GitHub Actions; inspect the draft PR checks for
actual execution results. Container build/startup is unverified locally. Never treat offline SQL
rendering or SQLite results as proof of PostgreSQL runtime correctness.

## Blockers

No licensed data/credentials or independently verified history was supplied. Real historical
backtest: BLOCKED. Independent calibration, schedule-archive integrity, event-ID reconciliation,
coverage and real-data reproducibility remain unverified. Production readiness is NO.

## V1 parallel regular/staging phase — 2026-10-27

- Full local suite after integrating the independent-reference changes: all available tests passed; Ruff and dependency integrity passed.
- Isolated advanced-staging migration 0003: upgrade, schema drift check, downgrade to 0002
  and re-upgrade passed. Actual local database upgraded without modifying basic observations.
- Wheel build includes advanced staging and the frozen regular-evaluation protocol resource.
- The actual authorized local regular cohort was evaluated through archived pregame inputs.
  Two identical runs produced identical prediction and evaluation artifacts. Outcome source
  bytes were revalidated only after forecasts were written. Details and metrics stay local.
- Synthetic forecast payloads are refused by the real scoring path. Future history, later
  schedule revisions, already-published target outcomes, stale captures and unresolved target
  quality fail the appropriate gates. Missing playoffs do not block a clean selected cohort.
- No real advanced batch was acquired, staged or promoted; staging remains isolated from the
  feature store. Public score captures never certify advanced-value historical availability.

Inspect the current draft PR checks for PostgreSQL and container verification on the final head.
The real assessment is a limited retrospective score-only baseline, not prospective validation,
calibration, profitability evidence or production acceptance.

## New temporal source-backed research run, 2026-11-03

The [locked temporal assessment](temporal-evaluation.md) reverified 142 private
historical captures and froze 402 forecasts before opening the adjudication
manifest. 298 games across three strata passed all fixed source/result/history
checks. Model and comparator used identical games and T-60 cutoffs. 102 forecasts
failed used-history quality and two failed target identity/schedule checks.
The 300-game planning target and primary seven-day uncertainty support gate
remain unmet. The three-day sensitivity interval is exploratory only.

Source/feature tests include original HTML and JSON digests, literal-only parsing,
explicit UTC display evidence, no invented table provider IDs, cutoff/future-data
rejection, replay receipt tampering, ambiguous identity quarantine, NBA Cup-final
exclusion, 2023 captures of the 2022–23 season without reusing 2022 test games,
locked code/cohort drift rejection and durable forecast writes before outcome
opening. Detailed reports and the exposure registry stay private. No advanced
rows or real odds were promoted; model and betting-edge validation remain open.

The measured source revision is 034abdbe4e273657cd9139928de918304246ad09.
Its exact locked replay produced identical prediction and evaluation hashes;
wheel packaging includes both new evaluators and the protocol resource. After
preserving the concurrently added research tools, the integrated suite passes
221 tests and Ruff. Exact private-report replay uses the measured revision;
the lock intentionally rejects a changed package file inventory.

## Audit remediation — 2026-11-05

- Ruff passed; 232 tests passed without a PYTHONPATH override. The installed-package
  subprocess smoke test runs outside the repository and removes PYTHONPATH explicitly.
- Missing/null/unknown overtime rules are rejected; CSV and Parquet regression tests
  reject exports without the explicit rule. Synthetic fixtures state their rule explicitly.
- API readiness requires supported schema revision 0003 and queryable mapped columns in
  every application table. Missing/old/unsupported revisions and incomplete tables return 503.
- Fixed-model backtests report pre-training-boundary targets as skips and continue with
  eligible targets; the exact cutoff boundary is covered.
- SQLite migration upgrade and schema-drift check, synthetic CLI HTML/JSON reporting,
  installed CLI status and dependency integrity passed after these changes.
- The local editable .pth file was repeatedly marked hidden. A local source-package
  symlink repairs imports across command sessions; see operations troubleshooting.
- PostgreSQL, Docker and GitHub CI for this remediation revision were not run locally.
  Production readiness remains blocked. Frozen historical predictions and results were
  not modified; exact historical replay continues to require its measured revision.


## Published remediation and adjudication follow-up — 2026-11-05

The remediation tree was published through the authenticated GitHub connector as
47bffeac3ad22c92ce88b0e0d9c57990f1beb5e0, preserving the previous remote parent and
without force-pushing. Its tree exactly matches local 5fb177a; the original local
commit chain remains on codex/local-audit-history-20261105.
[CI run 42078389259](https://github.com/Jambovisuaalit/betdoctore/actions/runs/42078389259)
passed installation, Ruff, PostgreSQL migrations/tests, synthetic reporting and Docker
Compose/API smoke. This is software verification, not production or model approval.

The subsequent adjudication overlay reverifies the approved decision, retained official
representations and all original result observations. The actual four-game overlay was
formed and read back successfully. New independent-sample capacity is zero with the newly
acquired two captures; the full exposure registry and 2022 exclusion remain enforced.
These subsequent code additions require their own CI result, separate from the run above.
See result-adjudication.md and next-independent-sample.md.
