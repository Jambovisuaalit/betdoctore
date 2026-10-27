# Independent regular-season identity reconciliation

This workflow is **separate from** the private FixtureDownload-based season-count audit.
A schedule cannot validate its own completeness. A verified **third-party event manifest**
is a required input: exact event IDs, local NBA dates, participants, home/away and phase.
A source's name or a second download does not prove independent upstream lineage.

## Input (local, never committed)

Place an authorized, separately sourced JSON array in
`data/coverage/independent/events.json`. Each record has:

```json
{
  "provider_event_id": "independent-provider-id",
  "season_end_year": 2022,
  "game_date": "2021-12-01",
  "home": "ATL",
  "away": "BOS",
  "phase": "regular_season",
  "date_basis": "america_new_york"
}
```

The provider must supply a unique event ID. Date is the local New York game date,
not an inferred UTC midnight. All known phase classifications must be explicit.
Use an **independent, licensed** manifest source; do not re-export FixtureDownload
or a downstream copy of FiveThirtyEight and call it independent.

Put a separate, manually reviewed provenance receipt at
`data/coverage/independent/provenance.json`:

```json
{
  "schema_version": 1,
  "provider_id": "independent-licensed-provider",
  "source_url": "https://provider.example/authorized-export",
  "terms_url": "https://provider.example/terms",
  "license_scope": "private_research",
  "source_sha256": "<sha256-of-exact-events-json-bytes>",
  "acquired_at": "2026-10-27T08:00:00+00:00",
  "lineage_reviewed": false,
  "reviewed_by": null,
  "review_evidence": null,
  "derived_from": []
}
```

The review flag must remain **false** until a human verifies the source's rights
and independence. When true, reviewer and reference to documented evidence are
required. The implementation verifies bytes and records the assertion but cannot
cryptographically prove publisher independence. Do not distribute private input
or detailed generated reports.

## Run

```sh
betdoctore regular-season-verify \
  data/coverage/independent/events.json \
  data/coverage/independent/provenance.json \
  --root data/results \
  --output data/coverage/approved \
  --as-of 2026-10-27
```

Requires existing private research inputs from `foundation-audit`.
No network/API calls or paid subscriptions are made by this command.

The output is immutable/content-addressed and deterministic:

- `<sha256>.summary.json`: compact season-level counts, reasons and status
- `<sha256>.regular-season-audit.json`: full local audit
- `2021-22-<sha256>.approved.json`: fully cross-matched **identity and score** records
- `2021-22-<sha256>.pending.json`: missing or single-source results
- `2021-22-<sha256>.quarantine.json`: ambiguous IDs, score/home/season conflicts

Equivalent season files are emitted for 2020-21 to 2025-26.

A game enters the **identity/score approved list** only when: the reference
is lineage-reviewed and separately sourced; the external event identity and season
match; at least two distinct result feeds agree on the final scores; no home/date,
result revision or key conflicts are present. Distinct feeds do not prove upstream
independence of the score content: each approved item makes that limitation explicit.

A season receives `IDENTITY_RESULT_LIST_COMPLETE` only when the reference has
exactly the expected 1,080/1,230 regular games, each team's 72/82-game balance
matches, no pending games or quarantines remain, and lineage review was recorded.
The full manifest remains independently reviewable; count matches alone do not
establish source completeness.

**This is not a training dataset.** Every accepted result has
`training_eligible: false`, and advanced statistics and historical T-60 gates
remain blocked. Final results may later be labels, never pregame features.
Postseason gaps do not block a distinct regular-season coverage report.
Avoid putting `data/` into Git or publishing its source-specific outputs.
