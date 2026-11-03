"""Locked, source-backed temporal assessment; private exports stay local.

Freeze every forecast before opening the current adjudication manifest. Source
snapshots are historical inputs: later snapshots cannot affect earlier cutoffs.
"""
import html
import json
import math
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from . import archived_exports, paired_evaluation, regular_evaluation
from .archived_exports import history_capacity, load_export, load_feed_inventory
from .paired_evaluation import compare
from .regular_evaluation import score_predictions, verify_outcome_sources
from .regular_season import target_gate
from .result_sources import sha256, write_once
from .season_audit import load_contract


def protocol() -> dict:
    return json.loads(files("betdoctore").joinpath("resources/temporal-evaluation-protocol.json").read_text())


def implementation() -> dict:
    return {module.__name__: sha256(Path(module.__file__).read_bytes())
            for module in (archived_exports, paired_evaluation, regular_evaluation)} | {
                __name__: sha256(Path(__file__).read_bytes()),
                "season_contract": sha256(json.dumps(load_contract(), sort_keys=True).encode()),
                **{p.stem: sha256(p.read_bytes()) for p in sorted(Path(__file__).parent.glob("*.py"))}}


def store_artifact(output: Path, suffix: str, value: dict) -> Path:
    raw = json.dumps(value, sort_keys=True, indent=2).encode()
    path = output/f"{sha256(raw)}.{suffix}.json"
    write_once(path, raw)
    return path


def load_locked_sources(plan: dict, directory: Path) -> list[dict]:
    snapshots = []
    for name, digest in plan["capture_receipts"].items():
        if Path(name).name != name or sha256((directory/name).read_bytes()) != digest:
            raise ValueError("Locked acquisition receipt changed")
        snapshots.append(load_export(directory, directory/name))
    feed = Path(plan["feed_inventory_path"])
    if sha256(feed.read_bytes()) != plan["feed_inventory_sha256"]:
        raise ValueError("Locked feed inventory changed")
    snapshots.extend(load_feed_inventory(feed.parent, feed))
    if not snapshots or not all(s["private_terms_verified"] for s in snapshots):
        raise ValueError("Private source terms not verified against reviewed bytes")
    return snapshots


def lock_plan(directory: Path, feed_inventory: Path, output: Path) -> Path:
    """No current outcome manifest is accepted or read by this operation."""
    spec = protocol()
    plan = {"protocol": spec, "created_at": datetime.now(UTC).isoformat(),
            "capture_receipts": {p.name: sha256(p.read_bytes())
                                 for p in sorted(directory.glob("*.capture-receipt.json"))},
            "feed_inventory_path": str(feed_inventory.resolve()),
            "feed_inventory_sha256": sha256(feed_inventory.read_bytes()),
            "implementation_sha256": implementation(),
            "mode": "retrospective_point_in_time_reconstruction",
            "current_outcome_manifest_opened": False}
    snapshots = load_locked_sources(plan, directory)
    capacity = history_capacity(snapshots, spec["maximum_history_capture_age_days"])
    plan["selected_keys"] = [r["game_key"] for r in capacity["candidates_with_history"]
                             if any(p["start"] <= r["game_key"].split(":")[1] <= p["end"]
                                    for p in spec["periods"])]
    plan["planning_capacity_games"] = len(plan["selected_keys"])
    plan["planning_target_met_before_source_admission"] = len(plan["selected_keys"]) >= spec["planning_minimum_games"]
    plan["source_admission"] = "PENDING_POST_FREEZE_ORIGINAL_BYTE_AND_RESULT_CHECKS"
    if not plan["selected_keys"]:
        raise ValueError("No source-backed candidates to lock")
    return store_artifact(output, "locked-plan", plan)


def freeze_forecasts(snapshots: list[dict], plan: dict) -> dict:
    """Pure forecasting: deliberately has no current outcome argument."""
    spec = plan["protocol"]
    capacity = history_capacity(snapshots, spec["maximum_history_capture_age_days"], include_history=True)
    selected = set(plan["selected_keys"])
    predictions = []
    for entry in capacity["candidates_with_history"]:
        if entry["game_key"] not in selected:
            continue
        target, history = entry["target"], entry["causal_history"]
        if int(target["game_date"][:4]) in spec["excluded_test_calendar_years"]:
            raise ValueError("Development-year target excluded")
        teams = {t: [r for r in history if t in r["teams"]][-spec["team_window"]:]
                 for t in target["teams"]}
        if min(len(v) for v in teams.values()) < spec["minimum_team_history"]:
            raise ValueError("Locked minimum history no longer met")
        league = history[-spec["league_window"]:]
        used = {r["game_key"]: r for records in [league, *teams.values()] for r in records}
        predictions.append({"game_key": target["game_key"], "home": target["home"],
                            "away": target["away"], "scheduled_tipoff": target["scheduled_tipoff"],
                            "prediction_cutoff": entry["cutoff"],
                            "prediction": sum(sum(r["total"] for r in hs)/len(hs)
                                              for hs in teams.values())/2,
                            "benchmark": sum(r["total"] for r in league)/len(league),
                            "used_history": [used[k] for k in sorted(used)],
                            "target_schedule_snapshot_sha256": target["snapshot_sha256"],
                            "cutoff_basis": "T-60 of archived scheduled time; actual tipoff unknown"})
    if {p["game_key"] for p in predictions} != selected or len(predictions) != len(selected):
        raise ValueError("Locked cohort changed during freeze")
    return {"protocol": spec, "predictions": predictions, "synthetic": spec["synthetic"],
            "current_adjudication_outcomes_read_during_forecasting": False,
            "production_ready": False}


def history_gate(prediction: dict, regular: dict) -> list[str]:
    by_key = {r["game_key"]: r for r in regular["games"]}
    failures = []
    for row in prediction["used_history"]:
        key = row["game_key"]
        result = by_key.get(key)
        if (not target_gate(regular, key)["passed"] or result is None
                or result["verification_status"] != "CROSS_PUBLISHER_CORROBORATED"):
            failures.append(f"UNVERIFIED_HISTORY:{key}")
            continue
        a, b = key.split(":")[2:]
        points = {a: result["points_a"], b: result["points_b"]}
        if (row["home"] != result["designated_home"]
                or row["total"] != sum(points.values())
                or row["score_identity"] != [points[row["home"]], points[row["away"]]]):
            failures.append(f"HISTORICAL_SCORE_OR_HOME_CONFLICT:{key}")
    return failures


def run_locked(plan_path: Path, directory: Path, manifest: Path, output: Path,
               result_root: Path = Path("data/results")) -> tuple[Path, dict]:
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    if plan["protocol"] != protocol() or plan["implementation_sha256"] != implementation():
        raise ValueError("Locked code/protocol changed: do not silently revise an evaluation")
    snapshots = load_locked_sources(plan, directory)
    frozen = freeze_forecasts(snapshots, plan)
    frozen["locked_plan_sha256"] = sha256(plan_bytes)
    frozen["implementation_sha256"] = plan["implementation_sha256"]
    prediction_path = store_artifact(output, "predictions", frozen)
    # No current outcome bytes are opened until all forecasts are durable.
    outcome_bytes = manifest.read_bytes()
    regular = json.loads(outcome_bytes)
    used_keys = {r["game_key"] for p in frozen["predictions"] for r in p["used_history"]}
    proofs = verify_outcome_sources(regular, set(plan["selected_keys"]) | used_keys, result_root)
    quality_excluded, admitted = [], []
    for prediction in frozen["predictions"]:
        errors = history_gate(prediction, regular)
        if errors:
            quality_excluded.append({"game_key": prediction["game_key"], "reasons": errors})
        else:
            admitted.append(prediction)
    result = score_predictions({**frozen, "predictions": admitted}, regular)
    result["forecast_count"] = len(frozen["predictions"])
    result["history_quality_exclusions"] = quality_excluded
    result["same_games_and_cutoffs_for_both_models"] = True
    result["source_admitted_games"] = len(result["scored"])
    result["period_counts"] = [{**p, "games": sum(p["start"] <= r["game_key"].split(":")[1] <= p["end"]
                                                       for r in result["scored"])}
                               for p in plan["protocol"]["periods"]]
    result["planning_target_met_after_source_admission"] = (
        len(result["scored"]) >= plan["protocol"]["planning_minimum_games"]
        and sum(p["games"] > 0 for p in result["period_counts"]) >= plan["protocol"]["planning_minimum_periods"])
    model, baseline = [], []
    for row in result["scored"]:
        row["paired_absolute_error_difference"] = abs(row["error"])-abs(row["benchmark_error"])
        row["paired_squared_error_difference"] = row["error"]**2-row["benchmark_error"]**2
        common = {"game_key": row["game_key"], "date": row["game_key"].split(":")[1],
                  "cutoff": row["prediction_cutoff"], "actual": row["actual_total"]}
        model.append({**common, "prediction": row["prediction"]})
        baseline.append({**common, "prediction": row["benchmark"]})
    settings = plan["protocol"]["bootstrap"]
    result["paired_analysis"] = []
    if model and all(p["games"] for p in result["period_counts"]):
        for block in [settings["block_days"], *settings["sensitivity_block_days"]]:
            result["paired_analysis"].append(compare(model, baseline, plan["protocol"]["periods"],
                block_days=block, repetitions=settings["repetitions"], seed=settings["seed"]))
    squared = [(r["prediction"]-r["actual_total"])**2
               -(r["benchmark"]-r["actual_total"])**2 for r in result["scored"]]
    result["paired_squared_error_difference"] = sum(squared)/len(squared) if squared else None
    result.update({"status": "COMPLETED_REAL_TEMPORAL_RECONSTRUCTION" if model else "BLOCKED_NO_ADMITTED_GAMES",
                   "locked_plan_sha256": sha256(plan_bytes), "prediction_artifact": prediction_path.name,
                   "prediction_sha256": sha256(prediction_path.read_bytes()),
                   "outcome_manifest_sha256": sha256(outcome_bytes), "outcome_source_proofs": proofs,
                   "implementation_sha256": implementation(), "protocol": plan["protocol"],
                   "model_validation_complete": False, "betting_edge_validated": False,
                   "production_ready": False,
                   "limitations": ["Retrospective source-availability-selected cohort, not prospective blind testing",
                                   "Uneven archive coverage; not a representative full-season claim",
                                   "Original source publishers may share upstream collection",
                                   "Scheduled T-60 only; actual tipoff not verified",
                                   "No advanced statistics, calibration, odds or betting profitability evaluated"]})
    if not all(math.isfinite(r["prediction"]) and math.isfinite(r["benchmark"]) for r in result["scored"]):
        raise ValueError("Nonfinite prediction")
    path = store_artifact(output, "evaluation", result)
    summary = {k: v for k, v in result.items() if k not in ("scored", "history_quality_exclusions", "excluded_at_scoring")}
    store_artifact(output, "summary", summary)
    document = '<!doctype html><html lang="fi"><meta charset="utf-8"><title>Temporal assessment</title><h1>Private source-backed assessment</h1><pre>'+html.escape(json.dumps(summary, indent=2))+'</pre></html>'
    write_once(path.with_suffix(".html"), document.encode())
    return path, result
