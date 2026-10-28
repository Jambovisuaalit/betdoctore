# Sportradar 2026 trial: NBA v8 / Synergy NBA read-only coverage gate

Account evidence supplied 2026-10-28:
- NBA API **Trial** 2026-10-17 to 2026-11-16
- Synergy Basketball NBA API **Trial** 2026-10-28 to 2026-11-27
- Each product 1,000 requests / **rolling 30 days**, not daily; trial default 1 QPS.
These are user-supplied account observations, not live contract/license verification.

Official docs:
- https://developer.sportradar.com/basketball/docs/nba-ig-historical-data
- https://developer.sportradar.com/basketball/reference/nba-game-summary
- https://developer.sportradar.com/basketball/reference/get_basketball-league-seasons
- https://developer.sportradar.com/basketball/reference/get_basketball-league-games
- https://developer.sportradar.com/basketball/reference/get_basketball-league-games-gameid-events
- https://developer.sportradar.com/getting-started/docs/authentication
- https://developer.sportradar.com/getting-started/docs/your-account

The standalone **opt-in** tool `python -m betdoctore.sportradar_trial_probe`
is not a data downloader or historical point-in-time admission path.
Only read-only API requests are used. It sends the key via an `x-api-key`
HTTP header and never logs/saves it. No redirects, retry loops,
unbounded pagination, arbitrary user-supplied endpoints or extra hosts.

`--scope nba --execute` makes **at most four** calls: season `2020`,
`2021`, `2022` `REG` schedules; plus at most one game summary from
the 2020 schedule with the deterministic earliest archived scheduled
time. The 2020 game selector ignores points and winner information.

`--scope synergy --execute` makes **at most three** calls: NBA seasons
(`take=25`), NBA games in December 1–3 **2021** (`take=2`), and
at most two possession events from one deterministically chosen game
(`take=2`). The Synergy trial may return historical seasons but not
grant data access for those seasons; 200 on seasons alone is not evidence
of accessible detailed games. Advanced analytical subscriptions are also
distinct from the basic Synergy event feed.

## Private safe usage in detached clean audit worktree

Use the separate `$HOME/Documents/betdoctore-history-review` worktree,
never switch or reset the original project with uncommitted edits.

```sh
ROOT="$HOME/Documents/betdoctore"
WORK="$HOME/Documents/betdoctore-history-review"
git -C "$ROOT" fetch origin feat/v1-regular-evaluation-staging
test -z "$(git -C "$WORK" status --porcelain)" || exit 1
git -C "$WORK" switch --detach origin/feat/v1-regular-evaluation-staging
mkdir -p "$ROOT/data/evaluation/sportradar-trial"
PYTHONPATH="$WORK/src" "$ROOT/.venv/bin/python" -m betdoctore.sportradar_trial_probe \
  --scope nba --output "$ROOT/data/evaluation/sportradar-trial" --execute
PYTHONPATH="$WORK/src" "$ROOT/.venv/bin/python" -m betdoctore.sportradar_trial_probe \
  --scope synergy --output "$ROOT/data/evaluation/sportradar-trial" --execute
```

The CLI requests a hidden key using `getpass` (or reads
`SPORTRADAR_API_KEY` from the **local process environment**).
Do not paste key into chat, terminal history, logs or Git.
No secret or raw response body is written. The hash-addressed private
receipt records endpoint, sanitized params, response start/end UTC,
HTTP status, SHA-256 bytes, bounded header metadata, JSON schema types,
and observed field *names* only. A `date`, `last-modified`,
`x-generated-date` or `etag` from a **2026 request** is **NOT**
proof of a 2020/2021/2022 or 2024/2025 original published snapshot.

No API calls were performed from GitHub CI; tests use MockTransport.
Under no condition does `--execute` admit historical as-of data,
verify a pre-T-60 source, lower the seven-day age requirement, approve
third-party data/AI/gambling usage or run model training. The original
18 schedule captures / 363 unscored prospective target fixtures stay
untouched. This is only a small old-cohort access and schema probe.

Rights remain separate: Sportradar trial entitlement does not establish
a data-storage, redistribution, commercial or gambling-model licence.
Inspect contract/terms before further ingestion. If 403/401/429 or
oversized response appears, the script stops within its bounded scope.
