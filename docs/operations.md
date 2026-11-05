# Operations and evidence

## Scope and assumptions

The issue's milestone list is the available specification; no separate Master Engineering
Specification was supplied. This implementation is a research baseline. No betting execution
exists. NBA full-game integer/half-point totals include overtime only when the source contract
confirms it. No injury feeds, lineup information, travel-distance model or optional CatBoost
residual implementation is included. Rest and back-to-back scheduling features are recorded;
the baseline uses pace and efficiency only. Do not interpret fitted parameters as a verified edge.

## Install and run

Python 3.11+ (tested 3.12):

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# Set DATABASE_URL to your PostgreSQL service (SQLite is available for local checks).
alembic upgrade head
ruff check .
pytest -q
betdoctore fixture-backtest
uvicorn betdoctore.api:app --host 127.0.0.1
```

`GET /health`, `/ready`, `/snapshots/{game_id}` and `/analysis/{game_id}` are read-only.
API analysis requires persisted snapshots and registered models. Keep the service on a trusted
network; authentication, public ingress and operational monitoring are deployment responsibilities.
The health endpoint does not imply database or production readiness. `/ready` requires the
supported Alembic revision (currently 0003) and queryable mapped columns in all application tables.
A healthy database response does not approve data coverage or the prediction model.

For Docker, set `POSTGRES_PASSWORD`, then `docker compose up --build`. The migration service runs
before API startup. Stop with `docker compose down`; retain the named database volume. Back up
PostgreSQL using `pg_dump` and test restores before operational use. Never downgrade production
without a backup and reviewed data-loss plan.

## Data contract and provenance

`Game` and `Odds` Pydantic schemas in `domain.py` are the import contracts. Use ISO 8601 timestamps
with UTC offsets. A game contains final points, possessions for each team, overtime periods,
actual tipoff/completion timestamps, team identifiers and a stable game identifier. Team identifiers
must be canonical across all sources. Odds carry decimal prices, exact line, bookmaker, full-game
settlement rules, source ID and timestamps. `includes_overtime` is mandatory: missing, null or
unknown rules are rejected during import. Obtain the value from the authorized source contract;
do not fill missing values with an assumed rule. Explicit false is retained but yields PASS for
the full-game overtime model. Both include `synthetic` (default false).

`observed_at` is when the source published/recorded the value; `available_at` is when the value was
available to the consuming research process. Use the later actual availability when uncertain.
Never backdate receipt of delayed or corrected records. Use a new source ID for corrections;
conflicting reuse is rejected. The current baseline expects one canonical final record per game;
resolve corrections/deduplicate before backtesting. It does not silently pick a revised history.
Archive reconstruction through HistoricalOddsAPI explicitly uses the provider archive timestamp
for historical availability. Retain original provider payloads and acquisition logs externally;
this repository does not claim archive publication timing proves actual live receipt.

```sh
betdoctore ingest-file games.csv game
betdoctore ingest-file odds.parquet odds
betdoctore feature-snapshot GAME_ID HOME AWAY 2024-01-01T20:00:00Z
betdoctore train games.json 2023-12-31T23:59:59Z
betdoctore register-model artifacts/DIGEST.json
betdoctore backtest games.json odds.json artifacts/DIGEST.json --walk-forward
```

JSON inputs are arrays of records. CLI ingestion commits valid records and reports invalid rows
with a nonzero exit code; duplicate identical records are idempotent. Store reports with the
source export. CSV/Parquet Pinnacle and bet365 adapters require already-authorized exports.
HistoricalOddsAPI supports the paid historical endpoint via explicit API key injection and
caller-confirmed overtime rules. It requests only exact-line paired totals; empty bookmaker
coverage remains empty, never inferred from another book. Event IDs must be reconciled to the
historical game source before evaluation. No credentials are bundled or logged deliberately.
Provider transport errors should be handled by the operator without logging secret request URLs.

## Point-in-time and model rules

Cutoff is tipoff minus 60 minutes. Completed games, observed statistics and availability must all
precede or equal cutoff. The current game is excluded. Rolling windows use ten prior games;
minimum five per team is required for a betting candidate. Pace is normalized to 48 minutes;
efficiency is points per 100 possessions. Snapshot hashes include source record contents and IDs.
Persisted snapshots are immutable by digest. Corrected historical tipoff times are not a substitute
for a point-in-time schedule archive; obtain that archive before asserting live reproducibility.

The baseline averages matchup pace and attack/defense ratings, then uses a discretized normal
regulation distribution plus an overtime mixture. Default spread/OT parameters are research
assumptions. Training fits bias, residual spread and OT frequency from previously available games,
using at least 50 chronological forecast residuals. This is parameter calibration, **not independent
calibration verification**. The optional CatBoost dependency is reserved for a later residual model.
Artifact content hashes, training boundary and training-record digest are recorded. Disk artifacts
are JSON, avoiding unsafe pickle loading. Independently verify artifact provenance before registering.

PASS applies to unavailable/stale odds, game/rule mismatch, insufficient history, uncalibrated
models, missing calibration evidence and EV below 4.5%. Odds age defaults to 120 minutes.
The model training boundary must not exceed cutoff. Fractional Kelly accounts for pushes and
caps a proposed research stake at 1% of available bankroll. Configuration validates bounds.

## Backtesting and interpretation

`--walk-forward` refits on records available at each prediction cutoff. Without it the explicitly
provided fixed artifact is used only after its training boundary. Earlier targets are recorded
as `MODEL_TRAINED_AFTER_CUTOFF` skips; later eligible targets continue. Equality at the cutoff is
allowed. No odds means a documented skip.
Latest eligible offer selection is deterministic before looking at results. Open stakes reserve
bankroll; profits affect subsequent stakes only after game completion and result availability. Returns assume completed
full-game markets; voided/cancelled bets need an explicit settlement feed and are outside the
completed-game input contract. CLV compares entry and last pre-tipoff same-book, same-line prices observed within ten minutes of tipoff;
missing matching closes are null. This price ratio differs from line-movement CLV.

Brier and log loss use Over/Under/Push classes. MAE/RMSE use total points. Metrics cover eligible
predictions only; report skipped coverage alongside them. ROI is null when no bets exist. Drawdown
uses settled bankroll, not intragame marks. Fixture reports are explicitly synthetic and are solely
software wiring evidence. They are not historical profitability or forecast-quality evidence.

## Delivery gates

- CODE_READY: baseline implementation passes local checks; PostgreSQL/CI and container results must
  be inspected before accepting a release. Optional CatBoost is not implemented.
- DATA_READY: PARTIAL. The technical basic-result foundation and selected archived schedules are
  verified. Complete regular-season coverage and historical input availability remain open;
  approved advanced statistics and real bookmaker snapshots are absent.
- FORECAST_EVALUATION_READY: the frozen 298-game score-only assessment is reproducible on its
  measured revision. The 300-game planning target and primary uncertainty gate remain unmet.
  This exposed cohort is not a new independent holdout.
- BACKTEST_READY: synthetic betting workflow verified; real-odds betting evaluation BLOCKED.
- PRODUCTION_READY: NO. Requires historical integrity, independent calibration, reproducibility,
  real-data backtest, PostgreSQL/container verification, reviewed deployment and monitoring.

Historical odds documentation: https://the-odds-api.com/historical-odds-data/ (paid archive).
NBA source restrictions: https://www.nba.com/termsofuse and https://www.nba.com/stats/help/faq.
Four official NBA report representations were retained through Firecrawl for private result
adjudication. They establish reviewed current report content, not historical T−60 availability
or original HTTP wire-byte identity. Advanced and odds datasets still require independently
reviewed sources and suitable usage rights. See [result adjudication](result-adjudication.md).

## Next acceptance steps

1. Supply the full master specification and resolve any differences from these assumptions.
2. Obtain authorized games/possessions, timestamped schedules and Pinnacle/bet365 snapshots;
   reconcile IDs, coverage, timezone, overtime/void rules and revision history.
3. Load and audit records; retain raw immutable exports, hashes and acquisition logs.
4. Run chronological calibration and an untouched holdout; inspect reliability by line, season
   and bookmaker, then freeze artifact and configuration hashes.
5. Run real-data walk-forward reports with transaction/market limits and missing-data coverage;
   compare independent reruns and inspect PostgreSQL CI and Docker startup evidence.
6. Review deployment authentication, backup restore, monitoring and alerting before release.


## Local editable-install troubleshooting

Verify installation without a `PYTHONPATH` workaround:

```sh
.venv/bin/python -c 'import betdoctore; print(betdoctore.__file__)'
.venv/bin/betdoctore status
```

On this macOS workspace, Python skipped the editable `.pth` file because it had the
filesystem `hidden` flag. Reinstalling alone preserved that flag. Inspect with
`ls -lO .venv/lib/python3.12/site-packages/__editable__.betdoctore-0.1.0.pth`;
if that specific file is marked hidden, remove its flag with
`chflags nohidden .venv/lib/python3.12/site-packages/__editable__.betdoctore-0.1.0.pth`
and repeat the checks in a separate command session. In this workspace the hidden flag
returned between sessions. A local source link was therefore added at
`.venv/lib/python3.12/site-packages/betdoctore` pointing to this repository's
`src/betdoctore` directory. This keeps imports attached to the source without depending on
`.pth` processing. The link is local and is not included in the distributed wheel.
If recreating this workaround, first ensure that the target path does not already contain
an installed package; do not overwrite it. A normal environment can use standard
`pip install -e '.[dev]'` without this workaround. Verify imports and CLI from outside the
repository as well. These are local filesystem repairs, not changes to Python's runtime.

`betdoctore status` describes documented research milestones. It does not inspect the local
database, execute tests, or query GitHub CI. Use `/ready` for schema readiness and retain
dated audit evidence for data/model/release decisions.
