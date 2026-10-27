# BALLDONTLIE Games — independent reference candidate

API: https://docs.balldontlie.io/
Terms: https://www.balldontlie.io/terms.html

The Games endpoint is free (API key required; 5 calls/minute), with event IDs,
season/phase filters, home and away teams, scores and historical games.
BALLDONTLIE is a **new provider**, not evidence of independent upstream
collection. Its terms permit lawful analytics but reserve third-party rights.

The importer fetches only `/v1/games` with `season_type=regular`,
seasons 2020 through 2025 (2020–21 through 2025–26). It excludes known
NBA Cup championship events and rejects season, ID and date inconsistencies.

## Run locally

1. Create a free API key at https://app.balldontlie.io/ and accept the terms.
2. On the Mac, set the key in your shell (never send it in chat or commit it):

```sh
export BALLDONTLIE_API_KEY='YOUR_LOCAL_KEY'
betdoctore reference-bdl-acquire
# Dry-run only; no HTTP requests.
betdoctore reference-bdl-acquire --execute --max-requests 100
```

At Free-tier 5 requests per minute, collection of six seasons requires
many calls. The CLI enforces a 12.5-second delay between requests, a maximum
request budget and fail-closed pagination. All records stay under ignored
`data/coverage/independent/balldontlie/`. Existing snapshots are never
overwritten. The importer does not purchase plans or access paid endpoints.

## Audit

The exporter writes `events.json`, `provenance.json`,
`date-quarantine.json` and `request-receipts.json`.
If BALLDONTLIE's date differs from the New York calendar date of its
timestamped tipoff, the exporter **does not guess which is correct**.
It records both fields and the provider event ID in the private
`date-quarantine.json`, excludes that event from the identity manifest,
and continues collecting remaining pages. Count/identity coverage therefore
remains BLOCKED for the affected season. This is **provider-level**
quarantine: it is separate from `regular-season-verify`'s cross-source
score/home quarantine and must be reviewed before approval.
No original API key or request header is stored.

The provider's `date` field is not silently rewritten to match the
timestamp. If a discrepancy is confirmed later, correct it through a
reviewed, separately versioned manifest; do not retroactively rewrite
`events.json`.

 The provenance receipt defaults to
`lineage_reviewed: false`: the audit will correctly leave rows pending.
Only after documented manual review of source lineage and permitted usage,
set reviewer, evidence and review flag on the **local** provenance file.

Run:

```sh
betdoctore regular-season-verify \
  data/coverage/independent/balldontlie/events.json \
  data/coverage/independent/balldontlie/provenance.json \
  --root data/results --output data/coverage/approved --as-of 2026-10-27
```

Season files distinguish approved identity-and-result matches, pending
single-source/undocumented matches and quarantined conflicts. A complete
league manifest and training eligibility are separate gates. The 7,557-game
private input is not accessible from GitHub; running this on the Mac is
necessary for **actual** season-level counts.

Do not publish the private source bundles or claim T−60 availability.
