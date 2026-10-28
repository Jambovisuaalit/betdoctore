# Historical NBA/ESPN source index — private metadata discovery

The previous outcome-blind inventory contains 18 schedule captures, 363
unscored future NBA games. The earlier exact Neil Paine CSV Wayback-CDX
query returned one capture, but zero that matched a seven-day
pre-T−60 window. This does **not** exclude other independently archived
NBA/ESPN sources. No source, holdout, model, or training gate is opened.

`python -m betdoctore.archive_source_index` investigates five *exact*
original URLs: NBA 2023/2024 full-season schedules; NBA rolling CDN
schedule; ESPN NBA scoreboard `dates=2024&limit=500` and
`dates=2025&limit=500`. These formats are exploratory candidates,
not evidence that Wayback preserved them, that they contain a complete
history, or that the data were licensed for modeling.

It queries **only** the Internet Archive CDX index with
`matchType=exact`, HTTP-200 filtering and no monthly collapse.
It retains the original 363 targets, seven-day freshness, and each
published-schedule T−60 cutoff. CDX request bytes, digest, full original
URL and index timestamps are written to a private, append-only local
directory. HTTP errors, malformed results and response truncation are
`INDEX_FAILED_NOT_ZERO`, not a claim of zero available sources.
A matching index timestamp is `TIMESTAMP_CANDIDATE_ONLY`.

Run from the already created clean, detached history-review worktree:

```sh
ROOT="$HOME/Documents/betdoctore"
WORK="$HOME/Documents/betdoctore-history-review"
git -C "$ROOT" fetch origin feat/v1-regular-evaluation-staging
test -z "$(git -C "$WORK" status --porcelain)" || exit 1
git -C "$WORK" switch --detach origin/feat/v1-regular-evaluation-staging
INV="$ROOT/data/evaluation/new-capture-inventory/3862cea977721f6627e98dabb4db0766d06b02a1993498ac2b1518658b9a9f3b.combined-inventory.json"
test -f "$INV" || exit 1
PYTHONPATH="$WORK/src" "$ROOT/.venv/bin/python" -m betdoctore.archive_source_index \
  --inventory "$INV" --output "$ROOT/data/evaluation/nba-espn-source-index"
PYTHONPATH="$WORK/src" "$ROOT/.venv/bin/python" -m betdoctore.archive_source_index \
  --inventory "$INV" --output "$ROOT/data/evaluation/nba-espn-source-index" \
  --execute-index
```

**Rights are a separate hard blocker.** Official NBA Terms of Use
(https://www.nba.com/termsofuse, updated 2026-07-13) explicitly
restrict NBA Statistics use connected to gambling, including lawful
gambling, absent appropriate permission. ESPN/Disney intellectual
property, copying, automated access and AI uses likewise require
source-specific permission review (https://disneytermsofuse.com/english/).
An archived capture is not a rights grant.

Even if an indexed archive matches an eligible T−60 instant, the next
body-verification stage remains separately gated. It must check exact
original URL, CDX digest versus original archived bytes, SHA-256, schema,
prior final-score histories, no target-outcome selection, game identity,
publication and source rights. **Do not download or approve archived
NBA/ESPN game-data bodies using this index tool.** This implementation
deliberately has no body-download or model-training command.

All outputs remain under ignored `data/` on the Mac. No original private
snapshots are uploaded. The PR stays Draft, `source_admitted_games=0`,
`periods_locked=false`, `training_eligible=false` and
`production_ready=false`.
