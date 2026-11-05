"""Verified append-only ground-truth overlay; never a historical feature correction."""
import json
from pathlib import Path

from .capture_inventory import save
from .regular_evaluation import verify_outcome_sources
from .result_sources import sha256

APPROVED_DECISION_SHA256 = 'e1a5f89b076440585f4d31c8e05de6afeacd482dc6119b61b43d111c0affd060'


def checked_json(path: Path, expected: str) -> dict:
    raw = path.read_bytes()
    if sha256(raw) != expected:
        raise ValueError('Adjudication evidence digest mismatch')
    return json.loads(raw)


def build_layer(manifest_path: Path, decision_path: Path, evidence_directory: Path,
                result_root: Path) -> dict:
    """Bind reviewed decisions to reverified original observations without altering them."""
    decision = checked_json(decision_path, APPROVED_DECISION_SHA256)
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if (decision['scope'] != 'PRIVATE_NONCOMMERCIAL_GROUND_TRUTH_ADJUDICATION_ONLY'
            or manifest['use_scope'] != 'private_noncommercial'
            or manifest['source_observations_rewritten'] is not False):
        raise ValueError('Unsupported adjudication scope')
    decisions = decision['decisions']
    keys = {d['game_key'] for d in decisions}
    if not keys or len(keys) != len(decisions):
        raise ValueError('Nonempty unique decisions required')
    # Existing verifier remains unchanged: dissenting source rows must still match bytes.
    proofs = verify_outcome_sources(manifest, keys, result_root)
    resolved = []
    for d in decisions:
        matches = [r for r in manifest['games'] if r['game_key'] == d['game_key']]
        if len(matches) != 1:
            raise ValueError('Adjudicated game must be unique in regular manifest')
        original = matches[0]
        if (original['phase'] != 'regular_season' or original['reasons'] != ['SCORE_CONFLICT']
                or original['result_consistency_passed'] is not False):
            raise ValueError('Only isolated score conflicts can be resolved')
        a, b = d['game_key'].split(':')[2:]
        if d['team_order'] != [a, b]:
            raise ValueError('Decision team orientation mismatch')
        name = d['evidence_file']
        if Path(name).name != name:
            raise ValueError('Evidence basename required')
        evidence = checked_json(evidence_directory / name, d['evidence_sha256'])
        meta = evidence['source']['metadata']
        if (evidence['url'] != d['source_url'] or meta['sourceURL'] != d['source_url']
                or meta['statusCode'] != 200 or not evidence['source']['rawHtml']
                or evidence['historical_availability_proven'] is not False
                or d['historical_t60_availability_proven'] is not False
                or d['historical_feature_replacement_authorized'] is not False):
            raise ValueError('Official representation contract mismatch')
        accepted = [r for r in original['observations']
                    if (r['points_a'], r['points_b']) == (d['points_a'], d['points_b'])]
        rejected = [r for r in original['observations'] if r not in accepted]
        rejected_scores = {(v['points_a'], v['points_b']) for v in d['rejected_score_variants']}
        if (not accepted or not rejected
                or {r['source'] for r in accepted} != {'neil-paine-nba-elo'}
                or {r['source'] for r in rejected} != {'fixturedownload-private'}
                or {(r['points_a'], r['points_b']) for r in rejected} != rejected_scores
                or any(r['designated_home'] != original['designated_home']
                       for r in original['observations'])):
            raise ValueError('Reviewed decision does not reconcile original source rows')
        resolved.append({
            'game_key': d['game_key'], 'points_a': d['points_a'], 'points_b': d['points_b'],
            'team_order': [a, b], 'designated_home': original['designated_home'],
            'status': 'GROUND_TRUTH_ADJUDICATED',
            'original_entry': original,
            'accepted_observation_references': accepted,
            'dissenting_observation_references': rejected,
            'official_evidence': {k: d[k] for k in
                                  ('source_url', 'evidence_file', 'evidence_sha256', 'evidence_grade')},
            'historical_feature_replacement_authorized': False,
            'historical_t60_availability_proven': False,
            'scheduled_tipoff_is_historically_verified': False,
        })
    return {'schema_version': 1, 'scope': 'private_noncommercial_ground_truth_only',
            'parent_manifest_sha256': sha256(raw),
            'decision_sha256': APPROVED_DECISION_SHA256,
            'decision_date': decision['decision_date'], 'games': resolved,
            'original_source_proofs': proofs, 'source_observations_rewritten': False,
            'frozen_evaluation_modified': False, 'historical_features_modified': False,
            'independent_test_ready': False, 'production_ready': False}


def persist_layer(manifest: Path, decision: Path, evidence: Path, result_root: Path,
                  output: Path) -> Path:
    layer = build_layer(manifest, decision, evidence, result_root)
    return output / save(output, 'adjudication-layer.json', layer)


def load_layer(path: Path, manifest: Path, decision: Path, evidence: Path,
               result_root: Path) -> dict:
    """Rebuild from verified evidence before exposing any resolved ground truth."""
    raw = path.read_bytes()
    if path.name != f'{sha256(raw)}.adjudication-layer.json':
        raise ValueError('Content-addressed adjudication layer required')
    recorded = json.loads(raw)
    rebuilt = build_layer(manifest, decision, evidence, result_root)
    if recorded != rebuilt:
        raise ValueError('Adjudication layer differs from verified evidence')
    return rebuilt


def ground_truth(layer: dict, game_key: str, *, purpose: str = 'ground_truth') -> dict:
    if purpose != 'ground_truth':
        raise ValueError('Adjudicated outcomes are not historical feature availability evidence')
    rows = [r for r in layer['games'] if r['game_key'] == game_key]
    if len(rows) != 1:
        raise ValueError('No unique adjudicated ground truth')
    return {k: rows[0][k] for k in ('game_key', 'points_a', 'points_b', 'team_order', 'status')}
