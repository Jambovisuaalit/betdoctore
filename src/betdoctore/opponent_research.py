"""Fail-closed validation of the Zhao/GCN research *hypothesis*, not ML training."""
import json
from importlib.resources import files

MODEL_ORDER = ("m0", "m1", "m2", "m3", "m4")
LEAKAGE_TOKENS = frozenset({
    "target_game_final_score", "target_game_efficiency_differential",
    "target_game_points", "target_game_pace", "target_game_offensive_rating",
    "target_game_defensive_rating", "future_game_result",
    "future_graph_edges", "future_lineups", "post_cutoff_injury_update",
})
ADVANCED = frozenset({"pace", "offensive_rating", "defensive_rating"})


def read_hypothesis_protocol() -> dict:
    return json.loads(files("betdoctore").joinpath(
        "resources/opponent-adjusted-research-protocol.json").read_text())


def validate_hypothesis_protocol(spec: dict) -> dict:
    """Reject future/target inputs and auto-admission; never authorizes training."""
    if spec.get("target") != "nba_regular_full_game_total_including_overtime":
        raise ValueError("Winner classification is not NBA totals regression")
    if spec.get("status") != "DRAFT_BLOCKED_UNTIL_POINT_IN_TIME_DATA_ADMISSION":
        raise ValueError("Research protocol must remain draft")
    evaluation = spec["evaluation"]
    if (evaluation["split"] != "strictly_chronological_walk_forward"
            or not evaluation["same_cohort_and_cutoffs_for_all_candidates"]
            or not evaluation["selection"] == "freeze_before_target_outcomes"
            or evaluation["min_distinct_periods"] < 2
            or evaluation["planning_min_games"] < 300
            or evaluation["seven_day_history_age_max"] != 7
            or evaluation["cutoff_minutes_before_archived_scheduled_tipoff"] != 60
            or not evaluation["validation_fit_only_training_side"]):
        raise ValueError("Chronology, freeze or comparison gates are missing")
    fields = spec["features"]
    score_inputs = fields["score_only_candidate"]
    advanced = fields["advanced_after_separate_approval"]
    prohibited = fields["prohibited_as_prediction_inputs"]
    if (not score_inputs or len(score_inputs) != len(set(score_inputs))
            or ADVANCED & set(score_inputs)
            or LEAKAGE_TOKENS & set(score_inputs)
            or LEAKAGE_TOKENS & set(advanced)
            or not LEAKAGE_TOKENS <= set(prohibited)):
        raise ValueError("Score-only features include advanced/target/future leakage")
    candidates = spec["candidates"]
    if tuple(m["id"] for m in candidates) != MODEL_ORDER:
        raise ValueError("Missing or reordered model comparisons")
    if any(m["advanced_required"] for m in candidates[:-1]):
        raise ValueError("Advanced feature admission required for baseline/first models")
    if (candidates[-1]["role"] != "DEFERRED_ABLATION_ONLY"
            or not candidates[-1]["advanced_required"]):
        raise ValueError("GCN must remain deferred")
    controls = spec["anti_leakage"]
    if not all(controls.values()):
        raise ValueError("All point-in-time and outcome-freeze controls are mandatory")
    if any(spec["gates"].values()):
        raise ValueError("Cannot authorize source admission, training or production by protocol")
    return {
        "status": "RESEARCH_DESIGN_ONLY",
        "models_defined": len(candidates),
        "score_only_new_models": ["m2", "m3"],
        "graph_model_deferred": True,
        "eligible_new_games": 0,
        "training_performed": False,
        "training_authorized": False,
        "advanced_data_promoted": False,
        "production_ready": False,
    }
