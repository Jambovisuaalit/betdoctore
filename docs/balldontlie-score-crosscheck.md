# BALLDONTLIE second score publisher — 2025–26 (private opt-in)

The 2025–26 FixtureDownload season has 1,230 games with one result
publisher. The previously acquired BALLDONTLIE Games API export stored
**event identities only**. Its same free Games endpoint also serves final scores
for the 2025–26 season. A *second publisher* is not automatically an
*independent upstream collector*.

This isolated read-only research adapter requests only `seasons[]=2025`
with `season_type=regular`, `per_page=100`, cursor pagination and
>=12.5-second spacing, with a maximum request budget. It compares all 1,230
event IDs, local-calendar dates and home/away assignments with the existing
checksum-verified identity export **before** accepting the score dataset. It
refuses incomplete seasons, missing scores, inconsistent IDs, and changed
dates, and writes no partial artifact on these errors.

Use an isolated clean worktree and existing private data. Dry run:
```sh
WORK="$HOME/Documents/betdoctore-audit"
ROOT="$HOME/Documents/betdoctore"
"$WORK/.venv/bin/python" -m betdoctore.bdl_score_audit \
  --reference "$ROOT/data/coverage/independent/balldontlie" \
  --output "$ROOT/data/coverage/independent/balldontlie-scores-2025" \
  --root "$ROOT/data/results" \
  --comparison-output "$ROOT/data/coverage/score-crosscheck-2025"
```
Add `--execute` to run the authenticated acquisition, after reviewing
BALDONTLIE's terms. The API key is requested using a hidden terminal
prompt and never saved to receipts. Request pacing is 5/minute or slower.
**Do not rerun the completed six-season 76-request identity import.**

Local-only files:
- `scores.json`: identity-linked canonical scores, zero approved
- `pages/*.json`: exact raw responses with digests
- `receipt.json`: digests, request metadata and use restrictions
- `score-crosscheck-2025/<digest>.summary.json`: aggregate comparison
- `score-crosscheck-2025/<digest>.score-comparison.json`: private details

Outcome labels explicitly use `TWO_PUBLISHER_SCORE_AGREEMENT_UNREVIEWED`
until license, provenance and upstream independence review. Date disputes
and the other 17 score conflicts remain separate.

No archive as-of availability, commercial use, training or deployment
entitlement is inferred.
