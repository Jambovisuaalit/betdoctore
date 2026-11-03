"""Synthetic causal forecast and durable-freeze tests; no real performance claims."""
import json
from datetime import UTC, datetime, timedelta

import pytest

from betdoctore import temporal_evaluation as evaluation


def synthetic_inputs():
    spec = {**evaluation.protocol(), "synthetic": True}
    day = datetime(2023, 11, 30, 7, tzinfo=UTC)
    rows = []
    for i in range(5):
        played = day-timedelta(days=i+1)
        rows.append({"provider_id": f"past:{i}", "game_key": f"nba:{played.date()}:BOS:MIA",
                     "game_date": str(played.date()), "teams": ["BOS", "MIA"], "home": "BOS", "away": "MIA",
                     "scheduled_tipoff": played.isoformat(), "season_end_year": 2024,
                     "public_available_by": day.isoformat(), "snapshot_sha256": "synthetic-only",
                     "total": 210+i, "score_identity": [110+i, 100]})
    target = {**rows[0], "provider_id": "target", "game_key": "nba:2023-11-30:BOS:MIA",
              "game_date": "2023-11-30", "scheduled_tipoff": "2023-12-01T00:00:00+00:00",
              "total": None, "score_identity": None}
    rows.append(target)
    plan = {"protocol": spec, "selected_keys": [target["game_key"]]}
    return [{"rows": rows}], plan


def test_both_forecasts_use_causal_same_cutoff():
    snapshots, plan = synthetic_inputs()
    frozen = evaluation.freeze_forecasts(snapshots, plan)
    row = frozen["predictions"][0]
    assert frozen["synthetic"]
    assert row["prediction"] == row["benchmark"] == 212
    assert row["prediction_cutoff"] == "2023-11-30T23:00:00+00:00"
    assert row["game_key"] not in {r["game_key"] for r in row["used_history"]}
    # A later source revision must not affect either earlier forecast.
    snapshots.append({"rows": [{**snapshots[0]["rows"][0], "total": 900,
                               "score_identity": [450, 450],
                               "public_available_by": "2023-12-01T01:00:00+00:00"}]})
    assert evaluation.freeze_forecasts(snapshots, plan) == frozen


def test_cohort_drift_and_input_conflict_fail_closed():
    snapshots, plan = synthetic_inputs()
    snapshots.append({"rows": [{**snapshots[0]["rows"][0], "score_identity": [111, 100]}]})
    with pytest.raises(ValueError, match="cohort"):
        evaluation.freeze_forecasts(snapshots, plan)


def test_history_gate_compares_orientation_and_original_scores():
    snapshots, plan = synthetic_inputs()
    row = evaluation.freeze_forecasts(snapshots, plan)["predictions"][0]
    regular = {"games": [{"game_key": r["game_key"], "result_consistency_passed": True,
                           "reasons": [], "verification_status": "CROSS_PUBLISHER_CORROBORATED",
                           "designated_home": "BOS", "points_a": r["score_identity"][0],
                           "points_b": r["score_identity"][1]} for r in row["used_history"]]}
    assert evaluation.history_gate(row, regular) == []
    regular["games"][0]["points_a"] += 1
    assert evaluation.history_gate(row, regular)[0].startswith("HISTORICAL_SCORE_OR_HOME_CONFLICT")


def test_predictions_durable_before_outcome_open(tmp_path, monkeypatch):
    snapshots, plan = synthetic_inputs()
    plan["implementation_sha256"] = {"synthetic": "only"}
    monkeypatch.setattr(evaluation, "implementation", lambda: {"synthetic": "only"})
    monkeypatch.setattr(evaluation, "protocol", lambda: plan["protocol"])
    monkeypatch.setattr(evaluation, "load_locked_sources", lambda plan, directory: snapshots)
    lock = evaluation.store_artifact(tmp_path, "locked-plan", plan)

    class Outcome:
        def read_bytes(self):
            predictions = list(tmp_path.glob("*.predictions.json"))
            assert len(predictions) == 1
            frozen = json.loads(predictions[0].read_text())
            assert not frozen["current_adjudication_outcomes_read_during_forecasting"]
            assert frozen["synthetic"]
            raise RuntimeError("Synthetic outcome-open sentinel")

    with pytest.raises(RuntimeError, match="sentinel"):
        evaluation.run_locked(lock, tmp_path, Outcome(), tmp_path)


def test_locked_implementation_changes_rejected_before_source_reads(tmp_path):
    _snapshots, plan = synthetic_inputs()
    plan["implementation_sha256"] = {"altered": "only"}
    lock = evaluation.store_artifact(tmp_path, "locked-plan", plan)
    with pytest.raises(ValueError, match="Locked code/protocol"):
        evaluation.run_locked(lock, tmp_path, tmp_path/"missing-outcomes", tmp_path)
