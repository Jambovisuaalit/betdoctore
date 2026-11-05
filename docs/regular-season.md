# Regular-season V1 scope and curation

V1 may evaluate a quality-approved **regular-season cohort** without waiting for playoff
completion or unrelated seasons to become complete. The user authorized parallel regular
completion and advanced staging. This changes the work-queue dependency, not the data-quality
requirements for an evaluated prediction.

`regular_season.build_regular_manifest` accepts the saved result observations, fixture source
catalogs, reviewed season contract and optional checksum-verified score-capture evidence. It
uses explicit fixture identities, removes the three known Cup championship identities, and
keeps archive playoff/non-regular observations out of the regular manifest. The broad archive
`non_playoff_unspecified` label is never sufficient to classify a game as regular season.

The manifest has independent queues:

- `regular_data_quality`: missing results, score/home/source-revision disagreements, catalog
  validation failures and opponent-identity anomalies.
- `regular_historical_availability`: no matching exact-score capture. A capture establishes
  public available-by evidence only; historical fixture and advanced-value availability still
  need their own evidence.
- `playoffs`: playoff and play-in completion work. These items explicitly do not block a clean
  regular-season evaluation cohort.

A matching current source game count cannot resolve identity problems. If a fixture-only
identity shares a date/participant with an otherwise excluded archive non-playoff observation,
the row is quarantined as a possible opponent-identity conflict. Source records are never
rewritten. A capture-supported conflicting score or replacement identity is retained as an
adjudication candidate with exact snapshot/row references, not applied silently.

`target_gate(manifest, game_key)` checks only that one target is uniquely in regular scope and
has no unresolved result/identity conflict. It deliberately does not read global playoff or
all-season completeness. Its returned historical schedule/feature gates remain false: the
cohort evaluator must verify the target's archived fixture identity, original scheduled cutoff,
causal feature/history availability, protocol freeze and all exclusion reasons separately.
Single-source consistent results remain labeled `SINGLE_SOURCE_UNVERIFIED`; consistency alone
is not independent validation. Advanced staging is never treated as feature approval.

`save_regular_manifest` writes content-addressed JSON, summary and HTML files under local ignored
`data/regular-season/`. The manifest can contain private non-commercial source observations,
so neither the raw manifest nor the detailed quality queue belongs in public Git/API responses.

The first real model assessment must disclose its exact clean cohort, skipped/quarantined
matches, score-only or advanced feature set, causal cutoff policy, source/protocol hashes and
chronological evaluation procedure. It must not claim full-league coverage or prospective
performance merely because a subset backtest executes. No wagering execution or invented odds
are introduced by this regular-season path.

The independent external-reference workflow (`regular-season-verify`) retains its own source
lineage/reviewer requirements. This curation manifest does not replace that review or silently
set an independent-source approval flag.
