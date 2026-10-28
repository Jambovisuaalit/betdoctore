# NBA prospective T−60 plan: offline only

Status: **PLAN ONLY — no live provider calls, licenses or training**.

## Governing rights reviewed 2026-10-28

Sportradar US Master Terms:
https://developer.sportradar.com/sportradar-updates/page/terms-and-conditions

- **Free Trial, clauses 3.1–3.2:** use only for non-commercial
  internal evaluation. No display/publication or competitive offering.
- **No Gambling, clause 2.10:** using the Products in connection with
  gambling/betting purposes requires Sportradar's **express written
  approval**. A successful API response is not such approval.
- Paid access, NBA official data and any additional addendum must be
  reviewed separately. Current **legal/procurement gate: BLOCKED**.
- One previously pasted API credential is exposed; explicitly confirm
  its provider-side revocation before more real calls.

Provider facts:
- NBA Daily Schedule:
  https://developer.sportradar.com/basketball/reference/nba-daily-schedule
  supplies league-day, scheduled tipoff, team ID/alias and game status.
  Active-day TTL ~10 minutes and schedule changes may occur in real time.
- 2025 basketball timestamp formatting:
  https://developer.sportradar.com/sportradar-updates/changelog/basketball-apis-new-timestamp-format
  allows both ISO 8601 `Z` and `+00:00` UTC timestamp forms.

## What was staged

`src/betdoctore/prospective_t60_plan.py` is a **purely local planner**
with no HTTP, authentication, scheduler, background task, data export
or model integration. The tool writes a content-hash-named, write-once
private plan under ignored `data/`; it never saves provider response
contents to GitHub. Use a *synthetic demo* now:

```sh
ROOT="$HOME/Documents/betdoctore"
WORK="$HOME/Documents/betdoctore-history-review"
OUT="$ROOT/data/evaluation/prospective-t60"
git -C "$ROOT" fetch origin feat/v1-regular-evaluation-staging &&
test -z "$(git -C "$WORK" status --porcelain)" &&
git -C "$WORK" switch --detach origin/feat/v1-regular-evaluation-staging &&
PYTHONPATH="$WORK/src" "$ROOT/.venv/bin/python" -m betdoctore.prospective_t60_plan \
  --demo --output "$OUT"
```

Once non-commercial evaluation of local NBA schedule data is verified
against the user's actual contract, an **already locally-held** future,
pregame Daily Schedule JSON can be evaluated with `--input FILE
--output "$OUT"`. The tool itself does not download that file.
Do not put any raw provider files or secrets in Git.

The planner only accepts NBA `REG` games that are wholly pregame
(`scheduled` or `created`), have valid UUIDs, unique IDs, distinct
team aliases, timezone-aware tipoff times, *no final scores/outcomes*,
and a T−60 deadline between 10 minutes and 7 days in the future.
It rejects complete/in-progress games and mixed postgame payloads
rather than selecting an evaluation cohort by completed outcomes.
It supports `+00:00` and `Z` ISO 8601 timestamps.

Each game has **two planned times** relative to scheduled tipoff:
`T−65` window start and `T−60` window end. These are *future
planning targets*, not verified pregame source captures. A genuine
future receipt would require provider application rights, a
server-controlled timestamp, exact endpoint and HTTP response metadata,
immutable bytes/hash, and publication/updated time evidence.
Any schedule changes, actual earlier tipoff, stale 10-minute cache or
source-history revisions require follow-up assessment. This plan does
NOT certify all mandatory pace/ORtg/DRtg, injury or odds features, or
the separate seven-day historical source freshness rule.

Immutable original 18 schedule capture snapshots / 363 outcome-blind
held-out targets are not read, imported, compared, reseeded or altered.
No `source_admitted_games`, `training_eligible` or
`production_ready` gate changes. No live scheduler, CI API calls,
manual scraping bypass, commercial launch or betting model training.
