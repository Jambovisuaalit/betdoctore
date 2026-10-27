# Historical NBA T-60 evidence gate (private offline audit)

**Goal:** Determine whether each feature value could have been available
at the actual betting-decision cutoff of T minus 60 minutes, **not**
whether a 2026 download happens to contain that value.

Status at 2026-10-27: **BLOCKED**. Nine archived public score captures
provide a later content-availability upper bound for selected scores;
they do **not** prove pregame odds, lineup, injury, prior-game advanced
statistics (Pace/ORtg/DRtg), or actual tipoff publication timestamps.
The NBA says advanced stats are generally updated 10–15 minutes after
games, but a current page is not a timestamped historical feature capture.

To inspect the evidence contract without an input:
```sh
"$HOME/Documents/betdoctore-audit/.venv/bin/python" -m betdoctore.t60_evidence
```

Future accepted private evidence is JSON:
```json
{
  "schema_version": 1,
  "games": [{
    "game_key": "nba:2025-12-01:ATL:BOS",
    "scheduled_tipoff": "2025-12-02T00:30:00Z",
    "actual_tipoff": "2025-12-02T00:30:00Z",
    "features": [{
      "name": "pace",
      "source_published_at": "2025-12-01T22:00:00Z",
      "archive_captured_at": "2025-12-01T23:10:00Z",
      "snapshot_observed_at": "2025-12-01T23:10:00Z",
      "source_game_completed_at": null,
      "snapshot_sha256": "<64-character verified checksum>",
      "evidence_kind": "independently_verified_capture"
    }]
  }]
}
```

The mandatory feature fields are `pace`, `ortg`, `drtg`,
`injury_status`, and `total_odds`; all must have timestamped
field-level sources. Historical bookmaker prices also must be no more
than 10 minutes old at T−60. The actual cutoff uses the **earlier**
verified scheduled/actual tipoff to avoid modeling post-start data.

Run:
```sh
python -m betdoctore.t60_evidence \
  --input /absolute/private/evidence.json \
  --output /absolute/private/t60-reports
```

The tool emits content-addressed private reports, flags missing/late
proof, and may mark `temporal_candidate=true` when claimed field
timestamps appear consistent. It **never** treats operator-entered
timestamps as verified archive chain-of-custody, source-independence, or
data-use rights. Accordingly `historical_t60_verified=false` and
`training_eligible=false` throughout this staging module.

No new production API ingestion, backdated availability times,
model training, deployment, or PR merge permitted.
