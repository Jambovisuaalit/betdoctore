"""Synthetic causal/evaluation fixtures only; real artifacts are never created by these tests."""
import json

import pytest

from betdoctore.regular_evaluation import freeze_predictions, load_protocol, score_predictions


def inputs():
    protocol = {**load_protocol(),"synthetic":True}
    history = [{"game_key":f"nba:2022-11-{i+1:02}:BKN:PHX","teams":["BKN","PHX"],
                "game_date":f"2022-11-{i+1:02}","total":200+i,"source_row":i+2,
                "public_available_by":"2022-12-06T22:42:08+00:00"} for i in range(10)]
    fixture = {"game_key":"nba:2022-12-06:BKN:PHX","home":"BKN","away":"PHX",
               "scheduled_tipoff":"2022-12-07T00:00:00+00:00",
               "schedule_available_by":"2022-12-06T20:00:00+00:00",
               "result_present_in_capture":False,"snapshot_sha256":"a"*64,"source_row":1}
    metadata = {"history_available_by":"2022-12-06T22:42:08+00:00","history_sha256":"b"*64}
    return history,[fixture],protocol,metadata


def outcome(frozen):
    prediction = frozen["predictions"][0]
    return {"use_scope":"private_noncommercial","work_queues":{"playoffs":[{"missing":999}]},
            "games":[{"game_key":prediction["game_key"],"result_consistency_passed":True,
                "reasons":[],"verification_status":"CROSS_PUBLISHER_CORROBORATED",
                "scheduled_tipoff":prediction["scheduled_tipoff"],"designated_home":"BKN",
                "points_a":100,"points_b":110,"observations":[{
                    "source":"synthetic-test-source","source_snapshot_sha256":"c"*64,
                    "source_row_numbers":[1]}]}]}


def test_forecast_is_causal_and_frozen_before_outcome_scoring():
    history,fixtures,protocol,meta = inputs()
    frozen = freeze_predictions(history,fixtures,protocol,meta)
    assert len(frozen["predictions"])==1
    prediction = frozen["predictions"][0]
    assert prediction["prediction"]==pytest.approx(204.5)
    assert prediction["prediction_cutoff"]=="2022-12-06T23:00:00+00:00"
    assert "actual_total" not in prediction
    future = {**history[-1],"total":999,"game_key":"nba:2022-12-05:BKN:PHX",
              "public_available_by":"2022-12-08T00:00:00+00:00"}
    assert freeze_predictions([*history,future],fixtures,protocol,meta)["predictions"]==frozen["predictions"]
    with pytest.raises(ValueError,match="synthetic"):
        score_predictions(frozen,outcome(frozen))
    report = score_predictions(frozen,outcome(frozen),real_evaluation=False)
    assert report["synthetic"] is True
    assert report["status"]=="COMPLETED_SYNTHETIC_TEST"
    assert report["model_metrics"]["mae"]==pytest.approx(5.5)
    assert report["playoff_completion_required"] is False
    changed = outcome(frozen)
    changed["games"][0]["points_a"] = 200
    score_predictions(frozen,changed,real_evaluation=False)
    assert frozen["predictions"][0]["prediction"]==prediction["prediction"]


def test_future_schedule_revisions_cannot_change_an_earlier_prediction():
    history,fixtures,protocol,meta = inputs()
    frozen = freeze_predictions(history,fixtures,protocol,meta)
    revised = {**fixtures[0],"scheduled_tipoff":"2022-12-07T02:00:00+00:00",
               "schedule_available_by":"2022-12-08T00:00:00+00:00",
               "result_present_in_capture":True,"snapshot_sha256":"d"*64}
    assert freeze_predictions(history,[*fixtures,revised],protocol,meta)["predictions"]==frozen["predictions"]
    revised["schedule_available_by"] = "2022-12-06T21:00:00+00:00"
    rejected = freeze_predictions(history,[*fixtures,revised],protocol,meta)
    assert rejected["predictions"]==[]
    assert rejected["excluded_before_outcomes"][0]["reason"]=="CONFLICTING_HISTORICAL_SCHEDULES"


@pytest.mark.parametrize("issue",["known_result","late_schedule","stale_history","short_history"])
def test_protocol_rejects_noncausal_or_unsupported_targets(issue):
    history,fixtures,protocol,meta = inputs()
    if issue=="known_result":
        fixtures[0]["result_present_in_capture"]=True
    elif issue=="late_schedule":
        fixtures[0]["schedule_available_by"]="2022-12-07T00:00:00+00:00"
    elif issue=="stale_history":
        fixtures[0]["scheduled_tipoff"]="2022-12-20T00:00:00+00:00"
    elif issue=="short_history":
        history=history[:2]
    result=freeze_predictions(history,fixtures,protocol,meta)
    assert result["predictions"]==[]
    assert result["excluded_before_outcomes"]


@pytest.mark.parametrize("issue",["conflict","single_source","changed_schedule","wrong_home"])
def test_outcome_quality_remains_mandatory_for_each_target(issue):
    frozen=freeze_predictions(*inputs())
    regular=outcome(frozen)
    if issue=="conflict":
        regular["games"][0].update(result_consistency_passed=False,reasons=["SCORE_CONFLICT"])
    elif issue=="single_source":
        regular["games"][0]["verification_status"]="SINGLE_SOURCE_UNVERIFIED"
    elif issue=="changed_schedule":
        regular["games"][0]["scheduled_tipoff"]="2022-12-07T01:00:00+00:00"
    elif issue=="wrong_home":
        regular["games"][0]["designated_home"]="PHX"
    report=score_predictions(frozen,regular,real_evaluation=False)
    assert report["model_metrics"]["n"]==0
    assert report["model_metrics"]["mae"] is None
    assert report["excluded_at_scoring"]


def test_prediction_artifact_is_written_before_the_outcome_manifest_is_read(tmp_path,monkeypatch):
    from betdoctore import regular_evaluation as module
    history,fixtures,protocol,meta=inputs()
    monkeypatch.setattr(module,"load_protocol",lambda:protocol)
    monkeypatch.setattr(module,"load_inputs",lambda *args:(history,fixtures,meta))
    with pytest.raises(FileNotFoundError):
        module.run_evaluation(tmp_path,tmp_path,tmp_path/"missing-outcomes.json",tmp_path/"reports")
    predictions=list((tmp_path/"reports").glob("*.predictions.json"))
    assert len(predictions)==1
    artifact=json.loads(predictions[0].read_text())
    assert artifact["outcome_data_read_during_forecasting"] is False
    assert "actual_total" not in artifact["predictions"][0]


def test_target_with_public_result_already_in_history_is_not_a_future_assessment():
    history,fixtures,protocol,meta=inputs()
    already_known={**history[-1],"game_key":fixtures[0]["game_key"]}
    result=freeze_predictions([*history,already_known],fixtures,protocol,meta)
    assert result["predictions"]==[]
    assert result["excluded_before_outcomes"][0]["reason"]=="TARGET_OUTCOME_ALREADY_IN_HISTORY_CAPTURE"
