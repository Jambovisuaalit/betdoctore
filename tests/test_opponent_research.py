"""Research paper hypothesis is inert until new historical evidence is admitted."""
import copy

import pytest

from betdoctore.opponent_research import (
    read_hypothesis_protocol,
    validate_hypothesis_protocol,
)


def spec():
    return read_hypothesis_protocol()


def test_paper_results_not_equated_with_nba_totals():
    value = spec()
    assert value["reference_paper"]["published_target"] == "NBA winner classification"
    assert value["target"] == "nba_regular_full_game_total_including_overtime"
    report = validate_hypothesis_protocol(value)
    assert report["training_performed"] is False
    assert report["training_authorized"] is False
    assert report["eligible_new_games"] == 0


def test_score_only_models_do_not_claim_advanced_eligibility():
    value = spec()
    assert {"pace", "offensive_rating", "defensive_rating"}.isdisjoint(
        value["features"]["score_only_candidate"])
    assert [m["id"] for m in value["candidates"]][-1] == "m4"
    assert validate_hypothesis_protocol(value)["graph_model_deferred"]


@pytest.mark.parametrize(("key", "changed"), [
    ("split", "random_shuffle"),
    ("selection", "pick_after_target_outcomes"),
    ("seven_day_history_age_max", 30),
    ("cutoff_minutes_before_archived_scheduled_tipoff", 0),
    ("min_distinct_periods", 1),
])
def test_temporal_guard_rejects_unsafe_protocol(key, changed):
    value = copy.deepcopy(spec())
    value["evaluation"][key] = changed
    with pytest.raises(ValueError):
        validate_hypothesis_protocol(value)


def test_reject_postgame_and_future_graph_edges():
    value = spec()
    value["features"]["score_only_candidate"].append("target_game_pace")
    with pytest.raises(ValueError, match="leakage"):
        validate_hypothesis_protocol(value)
    value = spec()
    value["features"]["advanced_after_separate_approval"].append("future_graph_edges")
    with pytest.raises(ValueError, match="leakage"):
        validate_hypothesis_protocol(value)


def test_no_automatic_unlock_even_from_manually_asserted_flag():
    value = spec()
    value["gates"]["real_new_model_training_authorized"] = True
    with pytest.raises(ValueError, match="Cannot authorize"):
        validate_hypothesis_protocol(value)


def test_gcn_must_be_deferred():
    value = spec()
    value["candidates"][-1]["role"] = "first_new_hypothesis"
    with pytest.raises(ValueError, match="deferred"):
        validate_hypothesis_protocol(value)
