# Verification evidence — 2026-10-27

## Local checks

- Editable package installation: passed on Python 3.12.14.
- Dependency integrity (`pip check`): passed.
- Ruff static analysis: passed.
- Pytest: 23 passed. One upstream Starlette/httpx deprecation warning.
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

Docker and PostgreSQL server binaries are unavailable in this local environment. Live PostgreSQL
migrations and integration tests are configured in GitHub Actions; inspect the draft PR checks for
actual execution results. Container build/startup is unverified locally. Never treat offline SQL
rendering or SQLite results as proof of PostgreSQL runtime correctness.

## Blockers

No licensed data/credentials or independently verified history was supplied. Real historical
backtest: BLOCKED. Independent calibration, schedule-archive integrity, event-ID reconciliation,
coverage and real-data reproducibility remain unverified. Production readiness is NO.
