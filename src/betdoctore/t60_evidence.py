"""Offline T-minus-60 evidence inventory; never certifies historical availability."""
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from .result_sources import sha256, write_once

REQUIRED_FEATURES = frozenset({
    "pace", "ortg", "drtg", "injury_status", "total_odds",
})
SCORE_AFTER_GAME_ONLY = frozenset({
    "target_final_score", "target_box_score", "target_play_by_play",
})


def _timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    v = datetime.fromisoformat(value)
    if v.utcoffset() is None:
        raise ValueError("T-60 audit requires timezone-aware timestamps")
    return v


def audit_target(target: dict) -> dict:
    """Temporal feasibility alone is not independent archived availability proof."""
    key = target["game_key"]
    scheduled = _timestamp(target.get("scheduled_tipoff"))
    actual = _timestamp(target.get("actual_tipoff"))
    reasons = []
    if not scheduled:
        reasons.append("SCHEDULED_TIPOFF_NOT_HISTORICALLY_VERIFIED")
    if not actual:
        reasons.append("ACTUAL_TIPOFF_NOT_HISTORICALLY_VERIFIED")
    cutoff = min(scheduled, actual) - timedelta(minutes=60) if scheduled and actual else None
    features, seen = [], set()
    for observation in target.get("features", []):
        name = observation["name"]
        if name in seen:
            raise ValueError(f"Duplicate feature evidence {key}:{name}")
        seen.add(name)
        problems = []
        if name in SCORE_AFTER_GAME_ONLY:
            problems.append("TARGET_GAME_POSTGAME_LEAKAGE")
        published = _timestamp(observation.get("source_published_at"))
        captured = _timestamp(observation.get("archive_captured_at"))
        observed = _timestamp(observation.get("snapshot_observed_at"))
        source_completion = _timestamp(observation.get("source_game_completed_at"))
        if not published:
            problems.append("PUBLICATION_TIME_NOT_VERIFIED")
        if not captured:
            problems.append("HISTORICAL_ARCHIVE_CAPTURE_MISSING")
        if not observed:
            problems.append("FEATURE_SNAPSHOT_TIME_MISSING")
        if cutoff:
            for label, ts in (
                ("PUBLICATION_AFTER_T60", published),
                ("ARCHIVE_CAPTURE_AFTER_T60", captured),
                ("SNAPSHOT_OBSERVED_AFTER_T60", observed),
                ("SOURCE_GAME_COMPLETED_AFTER_T60", source_completion),
            ):
                if ts and ts > cutoff:
                    problems.append(label)
            if name == "total_odds" and observed and cutoff-observed > timedelta(minutes=10):
                problems.append("ODDS_STALE_AT_T60")
        if observation.get("evidence_kind") != "independently_verified_capture":
            problems.append("CAPTURE_CHAIN_OF_CUSTODY_NOT_VERIFIED")
        digest = observation.get("snapshot_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(
            c not in "0123456789abcdef" for c in digest
        ):
            problems.append("SOURCE_SNAPSHOT_HASH_UNVERIFIED")
        # User-entered metadata alone does not cryptographically prove
        # publisher/public-archive capture times or upstream lineage.
        features.append({"name": name, "reasons": sorted(set(problems)),
                         "temporal_candidate": bool(cutoff) and not problems,
                         "archival_custody_independently_rechecked": False,
                         "t60_training_eligible": False})
    missing = sorted(REQUIRED_FEATURES - seen)
    if missing:
        reasons.append("REQUIRED_FEATURE_EVIDENCE_MISSING")
    if any(f["reasons"] for f in features):
        reasons.append("ONE_OR_MORE_FEATURE_EVIDENCE_BLOCKED")
    if not features:
        reasons.append("NO_HISTORICAL_FEATURE_EVIDENCE")
    return {
        "game_key": key, "conservative_cutoff": cutoff.isoformat() if cutoff else None,
        "missing_features": missing, "features": features,
        "reasons": sorted(set(reasons + [
            "ARCHIVE_AUTHENTICITY_AND_PUBLISHER_LINEAGE_NOT_INDEPENDENTLY_REVIEWED",
            "LICENSE_AND_ORIGINAL_PREMATCH_ODDS_NOT_VERIFIED",
        ])),
        "temporal_candidate": bool(cutoff and not missing and
                                  all(f["temporal_candidate"] for f in features)),
        "historical_t60_verified": False,
        "training_eligible": False,
    }


def audit_file(path: Path, output: Path) -> Path:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1 or not isinstance(payload.get("games"), list):
        raise ValueError("Expected schema_version=1 and games list")
    cases = [audit_target(game) for game in payload["games"]]
    keys = [x["game_key"] for x in cases]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate game keys")
    report = {"schema_version": 1, "source_input_sha256": sha256(path.read_bytes()),
              "target_count": len(cases),
              "temporal_candidate_count": sum(c["temporal_candidate"] for c in cases),
              "historical_t60_verified_count": 0,
              "training_eligible_count": 0,
              "blocker_reasons": dict(sorted(Counter(
                  reason for case in cases for reason in case["reasons"]).items())),
              "review_status": "BLOCKED_INDEPENDENT_AS_OF_EVIDENCE",
              "cases": cases}
    raw = json.dumps(report, sort_keys=True, indent=2).encode()
    digest = sha256(raw)
    summary = {k: v for k, v in report.items() if k != "cases"}
    summary["report_sha256"] = digest
    write_once(output / f"{digest}.t60-audit.json", raw)
    path = output / f"{digest}.summary.json"
    write_once(path, json.dumps(summary, sort_keys=True, indent=2).encode())
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.input is None or args.output is None:
        print(json.dumps({
            "status": "NO_HISTORICAL_T60_DATA_SUBMITTED",
            "minimum_evidence": sorted(REQUIRED_FEATURES),
            "requires": ["historical_scheduled_and_actual_tipoff",
                         "historical_publisher_publication_timestamp",
                         "independent_archive_capture_before_cutoff",
                         "immutable_content_verifiable_snapshot",
                         "licensing_and_upstream_lineage_review"],
            "historical_t60_verified_count": 0, "training_eligible": False
        }, indent=2))
        return
    path = audit_file(args.input, args.output)
    print(f"Private T-60 inventory: {path}")
    print(path.read_text())


if __name__ == "__main__":
    main()
