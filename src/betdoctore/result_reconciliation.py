"""Local-only cross-source audit. Corroboration is not proof of upstream independence."""
import html
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .result_sources import sha256, write_once
from .results import BasicResult


def reconcile(observations: list[BasicResult], start: date, end: date) -> dict:
    grouped = defaultdict(list)
    for record in observations:
        if start <= record.game_date <= end:
            grouped[record.game_key].append(record)
    accepted, quarantine = [], []
    single, confirmed = 0, 0
    sources = Counter()
    for key, records in sorted(grouped.items()):
        sources.update(r.source for r in records)
        issues = []
        if len({r.source for r in records}) != len(records):
            issues.append("MULTIPLE_REVISIONS_REQUIRE_REVIEW")
        if len({(r.points_a, r.points_b) for r in records}) != 1:
            issues.append("SCORE_CONFLICT")
        known_home = {r.designated_home for r in records if r.designated_home is not None}
        if len(known_home) > 1:
            issues.append("HOME_DESIGNATION_CONFLICT")
        if issues:
            quarantine.append({"game_key": key, "reasons": issues,
                               "observations": [r.model_dump(mode="json") for r in records]})
            continue
        supported = len({r.source for r in records}) >= 2
        confirmed += int(supported)
        single += int(not supported)
        # Field-level provenance stays attached; no manufactured merged tipoff/publication time.
        accepted.append({"game_key": key, "status": "CROSS_SOURCE_CORROBORATED" if supported
                         else "SINGLE_SOURCE_UNVERIFIED",
                         "observations": [r.model_dump(mode="json") for r in records]})
    # Flag likely date disagreements for manual review; never silently shift a date.
    signatures = defaultdict(list)
    for record in observations:
        signatures[(record.team_a, record.team_b, record.points_a, record.points_b)].append(record)
    possible_date_conflicts = []
    for records in signatures.values():
        for i, left in enumerate(records):
            for right in records[i+1:]:
                delta = abs((left.game_date-right.game_date).days)
                if left.source != right.source and 0 < delta <= 7:
                    possible_date_conflicts.append({"left": left.game_key, "right": right.game_key,
                                                    "days_apart": delta,
                                                    "status": "REVIEW_REQUIRED"})
    suspect_keys = {r[k] for r in possible_date_conflicts for k in ("left", "right")}
    # Potential date mismatches also stay out of the accepted working view.
    for entry in accepted[:]:
        if entry["game_key"] in suspect_keys:
            accepted.remove(entry)
            quarantine.append({**entry, "reasons": ["POSSIBLE_DATE_CONFLICT"]})
    years = Counter(date.fromisoformat(e["game_key"].split(":")[1]).year for e in accepted)
    return {"scope": {"start": str(start), "end": str(end)},
            "use_scope": "private_noncommercial", "redistribution_allowed": False,
            "observations": sum(sources.values()), "sources": dict(sources),
            "distinct_game_keys": len(grouped), "accepted_working_view": len(accepted),
            "cross_source_corroborated_before_date_review": confirmed,
            "single_source_before_date_review": single,
            "quarantined_game_keys": len(quarantine),
            "quarantine_reasons": dict(Counter(reason for q in quarantine for reason in q["reasons"])),
            "accepted_by_calendar_year": {str(y): years[y] for y in range(start.year, end.year+1)},
            "possible_date_conflicts": possible_date_conflicts,
            "independent_upstream_provenance_verified": False,
            "coverage_status": "UNVERIFIED", "ADVANCED_STATS_UNLOCKED": False,
            "gate_reasons": ["Score/home/date conflicts must be reviewed",
                             "Postseason/play-in and complete expected-game manifests missing",
                             "2025–2026 has substantial single-source coverage",
                             "Historical actual tipoff/publication timestamps unverified",
                             "Upstream source independence unverified"],
            "accepted": accepted, "quarantine": quarantine}


def save_reconciliation(report: dict, directory: Path) -> Path:
    raw = json.dumps(report, sort_keys=True, indent=2).encode()
    target = directory/f"{sha256(raw)}.reconciliation.json"
    write_once(target, raw)
    summary = {k: v for k, v in report.items() if k not in {"accepted", "quarantine"}}
    summary["detailed_report"] = target.name
    write_once(directory/f"{sha256(raw)}.summary.json",
               json.dumps(summary, sort_keys=True, indent=2).encode())
    document = ('<!doctype html><html lang="fi"><meta charset="utf-8">'
                '<title>BetDoctore — yksityinen eheysraportti</title>'
                '<h1>Tulosdatan eheys 2021–2026</h1>'
                '<p>Vain yksityiseen, ei-kaupalliseen tutkimukseen. '
                'Lähteet: Neil Paine / FiveThirtyEight ja FixtureDownload.com. '
                'Raakadataa tai tätä yksityiskohtaista raporttia ei julkaista.</p>'
                '<h2>Yhteenveto</h2><pre>'+html.escape(json.dumps(summary, indent=2))+'</pre>'
                '<h2>Karanteeni</h2><pre>'+html.escape(json.dumps(report["quarantine"], indent=2))
                +'</pre></html>')
    write_once(directory/f"{sha256(raw)}.html", document.encode())
    return target
