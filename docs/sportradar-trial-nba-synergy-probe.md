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

## Operator test findings and fail-closed remediation (2026-10-28)

The local operator ran the key-hidden read-only probe on detached commit
`3cf836f`. Actual results: **NBA 2020 REG schedule HTTP 401** (one call;
2021/2022 were not tested); **Synergy seasons HTTP 200**, then **Synergy
games HTTP 429** (two calls; no events requested). Private content-hash
receipts exist locally. This proves connectivity and limited Synergy season
endpoint access only. No rights, game events, or history was approved.

Official reference:
- https://developer.sportradar.com/getting-started/docs/response-codes
  defines 401 as lacking valid authentication to the requested resource,
  and 429 as either an exhausted quota or throttled request cadence.
- https://developer.sportradar.com/getting-started/docs/your-account
  explains application-specific master keys, products attached to each
  application and default 1 QPS / 1,000 rolling-30-day trial quota.
- https://developer.sportradar.com/basketball/reference/get_basketball-league-games
  confirms the Synergy Games endpoint and minDate/maxDate/skip/take.

**Before retrying NBA** check the Marketplace application hosting the
active *NBA API* trial and copy that application's own Master API Key.
The Synergy trial might belong to a different application; a successful
Synergy key is not proof the same key grants NBA API access. A 401 can
also reflect another entitlement or credential problem; it does not
establish that the 2020 schedule is unavailable.

**Before retrying Synergy** inspect its product Usage/QPS and Error Log
for the HTTP 429. Distinguish 30-day quota exhaustion from throttling;
with only two recorded calls this is not identifiable from the status
code alone. The follow-up probe now includes a conservative **3-second
interval**, saves allowlisted `Retry-After`, `X-RateLimit-Remaining`,
`X-RateLimit-Limit`, `X-RateLimit-Reset` and `X-Request-ID` headers
when present, and does **not** automatically retry a 429.

The program supports `SPORTRADAR_NBA_API_KEY` and
`SPORTRADAR_SYNERGY_API_KEY` as *optional local environment variables*,
falling back to `SPORTRADAR_API_KEY`; with none set, it prompts for the
correct **scope-specific** application master key invisibly. Do not
export keys in terminal commands/history, share them here, or store
raw provider response bodies. To avoid unnecessary calls, only rerun
after checking the correct product entitlement and the 429 rate/quota
status in the Sportradar portal. No CLI syntax, scoring threshold,
held-out game selection or training gate was changed.

## 2026-10-28 repeat 401 — final auth-only preflight

At clean detached commit `3aa82ea`, the operator again obtained **NBA
2020 REG schedule HTTP 401** (one call; no 2021/2022 schedule or summary).
The code's `x-api-key` header and the documented `/nba/trial/v8/en/games/2020/REG/schedule.json`
URL already match the Sportradar docs. See the official authentication
instructions: https://developer.sportradar.com/getting-started/docs/authentication
and historical URL: https://developer.sportradar.com/basketball/docs/nba-ig-historical-data.

Before another historical request, verify the actual NBA trial's **own
Application > Master API Key** in Marketplace. The app master key only
authorizes associated subscriptions. A 401 alone cannot prove whether
the wrong key, missing subscription attachment, an invalid key, or
another authentication issue caused the failure. Do not paste the key
in chat or into a GitHub issue.

For a safer one-call distinction, the CLI now supports **NBA-only
`--preflight-only`**, which calls the officially documented
`/nba/trial/v8/en/league/seasons.json` endpoint **exactly once**, using
header authentication. It will not call any dated schedule, target
fixture, boxscore or summary, regardless of the response. A 200
verifies access to this **specific Seasons endpoint now**, not to
historic game scores and not commercial or gambling-model rights.
A 401 after verification of the application master key should go to
Sportradar account support, not lead to repeated automated retries.

After confirming the application and its NBA subscription in the
portal, execute from the clean detached worktree:

```sh
ROOT="$HOME/Documents/betdoctore"
WORK="$HOME/Documents/betdoctore-history-review"
OUT="$ROOT/data/evaluation/sportradar-trial"
git -C "$ROOT" fetch origin feat/v1-regular-evaluation-staging &&
test -z "$(git -C "$WORK" status --porcelain)" &&
git -C "$WORK" switch --detach origin/feat/v1-regular-evaluation-staging &&
PYTHONPATH="$WORK/src" "$ROOT/.venv/bin/python" -m betdoctore.sportradar_trial_probe \
  --scope nba --preflight-only --output "$OUT" --execute
```

Never use the old `--scope nba --execute` until Seasons preflight
returns 200 and the product rights/terms have been evaluated.
The output writes only an append-only private metadata receipt,
never the API key, response body or player/game data.
