# BetDoctore

NBA full-game totals research platform with T−60 minute features, a possession/efficiency
baseline, parameter calibration, exact-line market analysis and chronological backtesting.
Read-only FastAPI service and Typer CLI. No wagering execution.

## Quick start

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
pip install --no-deps -e .
# Default local database is SQLite. Set DATABASE_URL for PostgreSQL.
alembic upgrade head
pytest -q
betdoctore fixture-backtest
uvicorn betdoctore.api:app
```

See [operations](docs/operations.md) for PostgreSQL/Docker setup, data contracts, ingestion,
model training, artifact registration, API analysis, point-in-time assumptions and acceptance gates.
See [verification evidence](docs/verification.md) for what was actually checked.

## Included

- Validated historical game/team-stat and odds records; CSV/Parquet imports and quality reports.
- Authorized Pinnacle/bet365 export adapters and paid historical-feed adapter.
- SQLAlchemy schema, frozen Alembic migration, immutable feature snapshots and model hashes.
- Rolling pace/ratings, rest/back-to-back features, delayed-data guards and overtime mixture.
- Over/Under/Push probabilities, margin/no-vig calculations, EV and push-aware fractional Kelly.
- PASS guards, 4.5% default EV threshold, stake cap and uncalibrated-model rejection.
- Fixed-artifact and refitting walk-forward backtests, settlements, same-line CLV, HTML/JSON reports.
- FastAPI reads, Typer commands, Docker Compose and PostgreSQL GitHub Actions verification.

## Readiness

| Gate | Status |
| --- | --- |
| CODE_READY | Baseline implemented; verification evidence linked above |
| DATA_READY | PARTIAL — curated regular cohorts; unresolved rows remain quarantined |
| FORECAST_EVALUATION_READY | Limited real score-only regular cohort assessed reproducibly |
| BETTING_BACKTEST_READY | BLOCKED — real odds and calibrated betting evaluation unverified |
| PRODUCTION_READY | NO — real-data calibration, reproducibility and backtesting unverified |

All bundled fixtures are explicitly synthetic. No real historical odds, accuracy, profitability
or calibration claims are made. The optional CatBoost residual extension is deferred.

## Real results foundation

[Basic-result acquisition and integrity workflow](docs/results-data.md) imports licensed archive
observations and user-authorized personal/non-commercial exports for 2021–2026. Private exports
and detailed reconciliation stay local; advanced features remain locked pending coverage and
conflict resolution. These imports do not establish real-data model/backtest readiness.

## Season and historical-availability audit

The [technical result foundation is accepted](docs/acceptance.md). The separate
[season/availability audit](docs/season-availability.md) checks season boundaries, Cup-final
exclusions, playoff series counts and checksum-verified public archive captures. It preserves
local receipt times and keeps the Pace/ORTG/DRTG join blocked pending the remaining evidence.

## V1 parallel work

[Regular-season curation](docs/regular-season.md) and [advanced staging](docs/advanced-staging.md)
proceed independently of the postseason backlog. The [first real score-only assessment](docs/regular-evaluation.md)
uses archived pregame schedules and causal result history; detailed private reports stay local.
Staged advanced rows are never automatically promoted, and missing playoffs do not veto a clean
regular evaluation cohort.
