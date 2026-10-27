# New capture inventory before sample locking

Run `betdoctore capture-inventory --private-research`. Detailed schedules, archive
responses, terms and receipts remain under ignored data/evaluation/new-capture-inventory/.
The command inventories NBA-2023, NBA-2024 and NBA-2025 FixtureDownload URL families
and rechecks existing post-2022 archived score payloads. It never reads the current
outcome manifest, freezes sample periods, generates forecasts or scores predictions.

Each successfully verified schedule capture records origin, archive UTC timestamp,
replay URL, retrieval timestamp, CDX index hash and archive SHA-1 payload digest,
local SHA-256, original payload location, terms hash and private noncommercial
scope. The archive timestamp proves availability by that time, not first publication.
FixtureDownload's [terms](https://fixturedownload.com/terms) limit local extraction
to personal noncommercial use; original exports are not published in Git or API.
Terms are retained for review, not treated as a general redistribution license.

The first completed inventory on 2026-10-27 found:

| Search | Indexed and payload-verified schedule captures |
| --- | ---: |
| NBA-2023 family, captures during 2023–2024 | 7 |
| NBA-2024 family, captures during 2024–2025 | 11 |
| NBA-2025 family, captures during 2025–2026 | 0 |

The 18 captures contain 363 distinct future schedule candidates with no result
present in the capture and an archive timestamp no later than scheduled T-60.
Candidates span February–April 2024 and November 2024–April 2025. These are
**candidates, not 363 admitted evaluation games**: regular-season identity,
reschedules, duplicate provider identities, source rights and causal history
still need admission. No sample periods were locked from these counts.

Six existing post-2022 score captures were byte/index reverified without parsing
new target outcomes. None meets the existing seven-day history freshness rule
at any of the 363 candidate cutoffs. A broader raw GitHub NBA-elo prefix search
returned only the already known April 2024 capture; a Substack prefix search
timed out. These searches do not prove that other eligible sources do not exist.
Failed requests and empty responses are recorded, not converted into evidence.

The combined local report has SHA-256
`3862cea977721f6627e98dabb4db0766d06b02a1993498ac2b1518658b9a9f3b`.
It records 0 timestamp-compatible candidates against the current score-history
inventory and 0 source-admitted new evaluation games. Score-capture license
review remains explicit and pending for new admission. No accuracy or betting
performance was calculated for this inventory.

Next: obtain and verify additional archived score-history inputs near the
candidate periods, or qualify another authorized source. Review licenses and
team-history coverage, then freeze two disjoint periods and the capture inventory
before opening new outcome totals. Do not relax the freshness rule after seeing
errors to reach 300 games. Reconstruct and save both model forecasts before
loading outcomes, then calculate paired MAE/RMSE and temporal-block uncertainty.
Advanced comparisons still require separately approved Pace/ORtg/DRtg evidence.
Production approval remains blocked pending separate model and betting-edge
validation. The 2022 development cohort remains excluded.
