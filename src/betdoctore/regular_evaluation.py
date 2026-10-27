"""A frozen, score-only regular-season assessment using actual archived pregame inputs.

Forecast generation cannot read current outcomes. Scoring is a separate second step.
Private schedule exports and detailed artifacts remain local, never in public Git/API.
"""
import base64
import csv
import hashlib
import html
import io
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .historical_availability import load_capture_index, verify_capture
from .private_results import NAMES, parse_private, verify_private
from .regular_season import target_gate
from .result_sources import sha256, verify_bundle, write_once
from .results import ALIASES, TEAMS, parse_neil_paine


def load_protocol() -> dict:
    return json.loads(files("betdoctore").joinpath("resources/regular-evaluation-protocol.json").read_text())


def acquire_schedule_captures(directory: Path, client: httpx.Client | None = None) -> dict:
    protocol = load_protocol()
    owned = client is None
    client = client or httpx.Client(timeout=90, follow_redirects=False)
    saved = []
    try:
        for row in protocol["schedule_captures"]:
            timestamp = row["timestamp"]
            meta_path = directory/f"{timestamp}.metadata.json"
            if not meta_path.exists():
                response = client.get("https://web.archive.org/cdx/search/cdx", params={
                    "url":row["original"],"output":"json","filter":"statuscode:200",
                    "from":"2022","to":"2022"})
                response.raise_for_status()
                index = response.json()
                if row not in [dict(zip(index[0],v,strict=True)) for v in index[1:]]:
                    raise ValueError("Pinned schedule capture absent from archive index")
                url = f"https://web.archive.org/web/{timestamp}id_/{row['original']}"
                capture = client.get(url)
                capture.raise_for_status()
                verify_schedule_bytes(capture.content,row,index)
                write_once(directory/f"{timestamp}.cdx.json",response.content)
                write_once(directory/f"{timestamp}.json",capture.content)
                write_once(meta_path,json.dumps({"cdx":row,"url":url,
                    "retrieved_at":datetime.now(UTC).isoformat(),"sha256":sha256(capture.content),
                    "private_noncommercial_only":True},sort_keys=True,indent=2).encode())
            raw = (directory/f"{timestamp}.json").read_bytes()
            index = json.loads((directory/f"{timestamp}.cdx.json").read_text())
            verify_schedule_bytes(raw,row,index)
            saved.append({"timestamp":timestamp,"sha256":sha256(raw),"original":row["original"]})
    finally:
        if owned:
            client.close()
    return {"captures":saved,"scope":"private_noncommercial"}


def verify_schedule_bytes(raw: bytes, row: dict, index: list):
    approved = load_protocol()["schedule_captures"]
    if row not in approved or row["mimetype"] != "application/json" or row["statuscode"] != "200":
        raise ValueError("Unapproved historical schedule capture")
    if row not in [dict(zip(index[0],v,strict=True)) for v in index[1:]]:
        raise ValueError("Historical schedule absent from CDX")
    digest = base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")
    if digest != row["digest"]:
        raise ValueError("Historical schedule checksum mismatch")
    if not isinstance(json.loads(raw),list):
        raise TypeError("Historical schedule must be a JSON array")


def load_inputs(history_directory: Path, schedule_directory: Path, protocol: dict):
    stamp = protocol["history_capture_timestamp"]
    raw = (history_directory/f"{stamp}.csv").read_bytes()
    metadata = json.loads((history_directory/f"{stamp}.metadata.json").read_text())
    verify_capture(raw,metadata["cdx"],load_capture_index(history_directory))
    if sha256(raw) != protocol["history_sha256"]:
        raise ValueError("Frozen history payload differs from protocol")
    captured = datetime.strptime(stamp,"%Y%m%d%H%M%S").replace(tzinfo=UTC)
    history = []
    for n,row in enumerate(csv.DictReader(io.StringIO(raw.decode())),start=2):
        if row["season"] != str(protocol["season_end_year"]) or row["playoff"]:
            continue
        if row["score1"] in {"","NA"} or row["score2"] in {"","NA"}:
            continue
        a,b = sorted(ALIASES.get(row[k],row[k]) for k in ("team1","team2"))
        if a not in TEAMS or b not in TEAMS or a==b:
            raise ValueError("Unknown captured regular participant")
        score1,score2 = int(row["score1"]),int(row["score2"])
        if min(score1,score2)<=0 or score1==score2 or row["date"]>str(captured.date()):
            raise ValueError("Invalid historical final score")
        history.append({"game_key":f"nba:{row['date']}:{a}:{b}","teams":[a,b],
                        "game_date":row["date"],"total":score1+score2,"source_row":n,
                        "public_available_by":captured.isoformat()})
    if len({h["game_key"] for h in history})!=len(history):
        raise ValueError("Duplicate captured history identity")
    fixtures, schedule_artifacts = [], []
    for row in protocol["schedule_captures"]:
        timestamp = row["timestamp"]
        body = (schedule_directory/f"{timestamp}.json").read_bytes()
        meta = json.loads((schedule_directory/f"{timestamp}.metadata.json").read_text())
        index = json.loads((schedule_directory/f"{timestamp}.cdx.json").read_text())
        verify_schedule_bytes(body,row,index)
        expected_url = f"https://web.archive.org/web/{timestamp}id_/{row['original']}"
        if meta["cdx"] != row or meta["url"] != expected_url or meta["sha256"] != sha256(body):
            raise ValueError("Schedule acquisition metadata conflict")
        source_time = datetime.strptime(timestamp,"%Y%m%d%H%M%S").replace(tzinfo=UTC)
        received = datetime.fromisoformat(meta["retrieved_at"])
        if received.utcoffset() is None or received<source_time:
            raise ValueError("Invalid schedule acquisition time")
        schedule_artifacts.append({"capture_url":expected_url,"sha256":sha256(body),
                                   "public_available_by":source_time.isoformat(),
                                   "receipt_sha256":sha256((schedule_directory/f"{timestamp}.metadata.json").read_bytes())})
        for number, item in enumerate(json.loads(body),start=1):
            tip = datetime.fromisoformat(item["DateUtc"])
            if tip.utcoffset() is None:
                raise ValueError("Archived schedule lacks timezone")
            home,away = NAMES[item["HomeTeam"]],NAMES[item["AwayTeam"]]
            a,b = sorted((home,away))
            day = tip.astimezone(ZoneInfo("America/New_York")).date()
            fixtures.append({"game_key":f"nba:{day}:{a}:{b}","home":home,"away":away,
                "scheduled_tipoff":tip.isoformat(),"schedule_available_by":source_time.isoformat(),
                "result_present_in_capture":item.get("HomeTeamScore") is not None
                    or item.get("AwayTeamScore") is not None or item.get("Winner") not in (None,""),
                "snapshot_sha256":sha256(body),"source_row":number})
    return history, fixtures, {"history_sha256":sha256(raw),"history_available_by":captured.isoformat(),
                              "schedule_captures":schedule_artifacts,
                              "history_receipt_sha256":sha256((history_directory/f"{stamp}.metadata.json").read_bytes())}


def freeze_predictions(history: list[dict],fixtures: list[dict],protocol: dict,inputs: dict) -> dict:
    """Pure causal forecast generation. Outcomes and current result manifests are not arguments."""
    history_time = datetime.fromisoformat(inputs["history_available_by"])
    window_end = history_time+timedelta(days=protocol["maximum_history_capture_age_days"])
    groups = defaultdict(list)
    for row in fixtures:
        groups[row["game_key"]].append(row)
    predictions, excluded = [], []
    for key, group in sorted(groups.items()):
        first_schedule = min(group,key=lambda r:(r["schedule_available_by"],r["snapshot_sha256"]))
        tip = datetime.fromisoformat(first_schedule["scheduled_tipoff"])
        if tip.utcoffset() is None:
            raise ValueError("Aware archived tipoff required")
        cutoff = tip-timedelta(minutes=protocol["prediction_cutoff_minutes"])
        if not history_time<=cutoff<=window_end:
            excluded.append({"game_key":key,"reason":"OUTSIDE_FROZEN_HISTORY_7_DAY_WINDOW"})
            continue
        known = [r for r in group if datetime.fromisoformat(r["schedule_available_by"])<=cutoff]
        if not known:
            excluded.append({"game_key":key,"reason":"NO_PREGAME_SCHEDULE_CAPTURE"})
            continue
        if len({r["scheduled_tipoff"] for r in known})!=1:
            excluded.append({"game_key":key,"reason":"CONFLICTING_HISTORICAL_SCHEDULES"})
            continue
        if any(r["result_present_in_capture"] for r in known):
            excluded.append({"game_key":key,"reason":"TARGET_RESULT_ALREADY_PRESENT"})
            continue
        identities = {(r["home"],r["away"]) for r in known}
        if len(identities)!=1:
            excluded.append({"game_key":key,"reason":"CONFLICTING_PUBLISHED_PARTICIPANTS"})
            continue
        home,away = next(iter(identities))
        if any(h["game_key"]==key and datetime.fromisoformat(h["public_available_by"])<=cutoff
               for h in history):
            excluded.append({"game_key":key,"reason":"TARGET_OUTCOME_ALREADY_IN_HISTORY_CAPTURE"})
            continue
        eligible = sorted((h for h in history if h["game_key"]!=key
                            and datetime.fromisoformat(h["public_available_by"])<=cutoff),
                           key=lambda h:(h["game_date"],h["game_key"]))
        team_history = {t:[h for h in eligible if t in h["teams"]][-protocol["team_window"]:]
                        for t in (home,away)}
        if min(len(v) for v in team_history.values())<protocol["minimum_team_history"]:
            excluded.append({"game_key":key,"reason":"INSUFFICIENT_CAUSAL_TEAM_HISTORY"})
            continue
        league = eligible[-protocol["league_window"]:]
        if not league:
            excluded.append({"game_key":key,"reason":"NO_CAUSAL_LEAGUE_HISTORY"})
            continue
        means = {t:sum(x["total"] for x in hs)/len(hs) for t,hs in team_history.items()}
        predictions.append({"game_key":key,"home":home,"away":away,
            "scheduled_tipoff":tip.isoformat(),"prediction_cutoff":cutoff.isoformat(),
            "cutoff_basis":"T-60 of published archived schedule; actual tipoff not asserted",
            "prediction":(means[home]+means[away])/2,
            "benchmark":sum(h["total"] for h in league)/len(league),
            "team_history_keys":{t:[h["game_key"] for h in hs] for t,hs in team_history.items()},
            "league_history_keys":[h["game_key"] for h in league],
            "schedule_snapshot_sha256":sorted({r["snapshot_sha256"] for r in known}),
            "history_capture_age_hours":(cutoff-history_time).total_seconds()/3600})
    return {"schema_version":1,"protocol":protocol,"protocol_sha256":sha256(
                json.dumps(protocol,sort_keys=True).encode()),"inputs":inputs,
            "predictions":predictions,"excluded_before_outcomes":excluded,
            "outcome_data_read_during_forecasting":False,
            "evaluator_source_sha256":sha256(Path(__file__).read_bytes()),"synthetic":protocol["synthetic"],
            "mode":"retrospective_point_in_time_reconstruction","scope":"private_noncommercial"}


def score_predictions(frozen: dict,regular: dict,real_evaluation: bool = True) -> dict:
    if real_evaluation and frozen["synthetic"]:
        raise ValueError("Real evaluation cannot score synthetic forecasts")
    by_key = {r["game_key"]:r for r in regular["games"]}
    scored,excluded = [],[]
    for prediction in frozen["predictions"]:
        key = prediction["game_key"]
        gate = target_gate(regular,key)
        if not gate["passed"]:
            excluded.append({"game_key":key,"reasons":gate["reasons"]})
            continue
        outcome = by_key[key]
        reasons = []
        if outcome["verification_status"]!="CROSS_PUBLISHER_CORROBORATED":
            reasons.append("OUTCOME_REQUIRES_TWO_CORROBORATING_PUBLISHERS")
        if outcome["scheduled_tipoff"] is None or datetime.fromisoformat(outcome["scheduled_tipoff"])!=datetime.fromisoformat(prediction["scheduled_tipoff"]):
            reasons.append("CURRENT_AND_ARCHIVED_SCHEDULE_NOT_RECONCILED")
        if outcome["designated_home"]!=prediction["home"]:
            reasons.append("HOME_IDENTITY_NOT_RECONCILED")
        if reasons:
            excluded.append({"game_key":key,"reasons":reasons})
            continue
        total = outcome["points_a"]+outcome["points_b"]
        scored.append({**prediction,"actual_total":total,
            "error":prediction["prediction"]-total,"benchmark_error":prediction["benchmark"]-total,
            "outcome_source_references":[{"source":r["source"],"snapshot_sha256":r["source_snapshot_sha256"],
                                          "rows":r["source_row_numbers"]} for r in outcome["observations"]]})
    def metrics(field):
        if not scored:
            return {"n":0,"mae":None,"rmse":None,"mean_error":None}
        errors = [r[field] for r in scored]
        return {"n":len(errors),"mae":sum(abs(x) for x in errors)/len(errors),
                "rmse":math.sqrt(sum(x*x for x in errors)/len(errors)),"mean_error":sum(errors)/len(errors)}
    return {"status":("COMPLETED_SYNTHETIC_TEST" if frozen["synthetic"] else "COMPLETED_REAL_LIMITED_COHORT")
                     if scored else "BLOCKED_NO_SCORABLE_TARGETS",
            "synthetic":frozen["synthetic"],"scope":"private_noncommercial",
            "model_metrics":metrics("error"),"benchmark_metrics":metrics("benchmark_error"),
            "forecast_count":len(frozen["predictions"]),"scored":scored,"excluded_at_scoring":excluded,
            "exclusion_counts":dict(Counter(reason for x in excluded for reason in x["reasons"])),
            "playoff_completion_required":False,"advanced_metrics_used":False,
            "limitations":["Small archive-availability-selected five-team schedule cohort",
                "Retrospective reconstruction, not a prospective untouched test",
                "History is frozen at one observed capture, with an explicit seven-day age cap",
                "Cutoff uses historical published scheduled time; actual tipoff is not asserted",
                "Corroborating publishers do not prove independent original collection",
                "No odds, calibration, ROI or profitability evaluated"],"production_ready":False}


def verify_outcome_sources(regular: dict,keys: set[str],root: Path) -> list[dict]:
    """Revalidate only the selected cohort against original saved source bytes.

    No unrelated season or playoff file is required. Runs after prediction freeze.
    """
    entries = [r for r in regular["games"] if r["game_key"] in keys]
    if not entries:
        return []
    start = min(date.fromisoformat(k.split(":")[1]) for k in keys)
    end = max(date.fromisoformat(k.split(":")[1]) for k in keys)
    archive = root/"neil-paine"
    manifest = verify_bundle(archive)
    rows,report = parse_neil_paine(list(csv.DictReader((archive/"source.csv").read_text().splitlines())),
        manifest["sha256"],datetime.fromisoformat(manifest["retrieved_at"]),start,end)
    if report["errors"]:
        raise ValueError("Outcome archive failed structural verification")
    verified = {(r.source,r.game_key):r.model_dump(mode="json") for r in rows}
    proofs = [{"source":manifest["source"],"sha256":manifest["sha256"]}]
    for season in sorted({r["season_end_year"] for r in entries}):
        directory = root/"private-fixturedownload"/str(season-1)
        private = verify_private(directory)
        rows,report = parse_private(json.loads((directory/"source.json").read_text()),private,start,end)
        if report["errors"]:
            raise ValueError("Outcome private source failed structural verification")
        verified.update({(r.source,r.game_key):r.model_dump(mode="json") for r in rows})
        proofs.append({"source":private["source"],"sha256":private["sha256"]})
    for entry in entries:
        for claimed in entry["observations"]:
            actual = verified.get((claimed["source"],entry["game_key"]))
            if actual is None or actual!=claimed:
                raise ValueError("Curated outcome does not match original verified source bytes")
        if entry["result_consistency_passed"]:
            names = {r["source"] for r in entry["observations"]}
            if (entry["verification_status"]=="CROSS_PUBLISHER_CORROBORATED"
                    and not {"neil-paine-nba-elo","fixturedownload-private"}<=names):
                raise ValueError("Real outcome lacks two byte-verified publishers")
            totals = {(r["points_a"],r["points_b"]) for r in entry["observations"]}
            if totals!={(entry["points_a"],entry["points_b"])}:
                raise ValueError("Curated outcome totals differ from original observations")
    return proofs


def run_evaluation(history_directory: Path,schedule_directory: Path,regular_manifest: Path,output: Path,result_root: Path = Path("data/results")):
    protocol = load_protocol()
    history,fixtures,inputs = load_inputs(history_directory,schedule_directory,protocol)
    frozen = freeze_predictions(history,fixtures,protocol,inputs)
    raw_predictions = json.dumps(frozen,sort_keys=True,indent=2).encode()
    prediction_id = sha256(raw_predictions)
    prediction_path = output/f"{prediction_id}.predictions.json"
    write_once(prediction_path,raw_predictions)
    # Only after predictions have been durably frozen do we read outcomes.
    outcome_bytes = regular_manifest.read_bytes()
    regular = json.loads(outcome_bytes)
    proofs = verify_outcome_sources(regular,{r["game_key"] for r in frozen["predictions"]},result_root)
    result = score_predictions(frozen,regular)
    result["outcome_source_bytes_revalidated"] = True
    result["outcome_source_proofs"] = proofs
    result.update({"protocol_sha256":frozen["protocol_sha256"],
                   "evaluator_source_sha256":frozen["evaluator_source_sha256"],"prediction_sha256":prediction_id,
                   "prediction_artifact":prediction_path.name,"outcome_manifest_sha256":sha256(outcome_bytes),
                   "inputs":inputs,"excluded_before_outcomes":frozen["excluded_before_outcomes"]})
    raw = json.dumps(result,sort_keys=True,indent=2).encode()
    identity = sha256(raw)
    path = output/f"{identity}.evaluation.json"
    write_once(path,raw)
    summary = {k:v for k,v in result.items() if k not in {"scored","excluded_before_outcomes"}}
    write_once(output/f"{identity}.summary.json",json.dumps(summary,sort_keys=True,indent=2).encode())
    document = ('<!doctype html><html lang="fi"><meta charset="utf-8"><title>BetDoctore aito baseline-arvio</title>'
        '<h1>Runkosarjan score-only baseline</h1><p>Oikea historiallinen aineisto. Yksityinen, ei-kaupallinen '
        'tutkimus. Rajattu retrospektiivinen arvio; ei tuotantohyväksyntää.</p><pre>'
        +html.escape(json.dumps(summary,indent=2))+'</pre></html>')
    write_once(output/f"{identity}.html",document.encode())
    return path,result
