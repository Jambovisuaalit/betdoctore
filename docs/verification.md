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
