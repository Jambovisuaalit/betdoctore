# Private result conflict decisions — 2026-11-05

Four reviewed official NBA publications support the following results, with teams in
canonical game-key order:

| Game key | Accepted points | Conflicting FixtureDownload points |
| --- | --- | --- |
| nba:2023-10-25:LAC:POR | 123–111 | 126–111 |
| nba:2024-01-23:NOP:UTA | 153–124 | 153–24 |
| nba:2024-11-02:MEM:PHI | 124–107 | 124–104 |
| nba:2025-01-25:MEM:UTA | 125–103 | 123–103 |

Official evidence URLs and exact retained representation hashes are pinned in
`scripts/adjudicate_result_conflicts.py`. Run from the repository root:

```sh
PYTHONPATH=src .venv/bin/python scripts/adjudicate_result_conflicts.py
```

The command requires private evidence already present under
`data/evaluation/primary-result-evidence/` and the original hashed conflict audit.
It verifies the files before issuing a content-addressed, append-only JSON decision.
Missing, changed, unsuccessful, or mismatched evidence fails closed. These are
explicit reviewed cases, not a general score extraction algorithm.

The private decision artifact is
`e1a5f89b076440585f4d31c8e05de6afeacd482dc6119b61b43d111c0affd060.result-adjudication.json`.
The hash identifies the saved decision bytes. Its source hashes identify retained
Firecrawl representations containing raw HTML, Markdown and provider metadata.
They do not establish original HTTP wire-byte identity. Earlier HTTP 403 response
hashes are not result evidence. The four accepted scores agree with the reviewed
Neil Paine results; repeated FixtureDownload captures are one publisher.

This decision resolves the reviewed score conflict for ground-truth review only.
It does not modify source observations, the regular-season manifest, frozen
forecasts or the frozen 298-game assessment. Existing feature conflict exclusions
remain in place. The new `result_adjudication` overlay verifies the reviewed decision hash, the retained
official representations, and each original result observation through the existing byte verifier.
It retains the complete original quarantined entry and separate accepted/dissenting references.
It never marks the original observations mutually consistent.

Current official pages and their stated publication dates do not prove historical
T−60 availability. Do not replace historical observed scores with these corrected
values as if the correction were known before prediction. Any revised assessment
must preserve the original exposure registry and be labeled as a revision, not a
new independent test. Longer temporal coverage, advanced source admission,
betting-edge validation and production approval remain open.


## Verified overlay

```sh
betdoctore adjudicate-results \
  data/regular-season/6a9e71de8d2edb51509a6d48258d5d871c00103828c3c7a45e3ae29d97d5cfc8.regular-manifest.json \
  data/evaluation/primary-result-evidence/e1a5f89b076440585f4d31c8e05de6afeacd482dc6119b61b43d111c0affd060.result-adjudication.json
```

The actual private overlay is
`5d8c9b9d71696a2b879ec62cf8bdc487f324d74c8d60b0f4c83ea74e03545181.adjudication-layer.json`
under `data/regular-season/adjudication/`. It resolves exactly the four reviewed ground-truth
scores. Isolated score conflicts are supported; identity/home conflicts fail closed.
`betdoctore adjudicated-result GAME_KEY LAYER MANIFEST DECISION` rebuilds and verifies the
layer before returning a result. A changed official file, decision, original source row, layer,
or parent manifest causes rejection. Historical-feature use is explicitly rejected.

The old evaluator and `target_gate` are unchanged. Neither automatically reads this overlay,
and the old 102 feature-quality exclusions remain in place. Any future evaluator that opts
into adjudicated ground truth must bind the overlay hash in its own protocol; it may not use
corrected values as historical inputs without separate availability evidence.
