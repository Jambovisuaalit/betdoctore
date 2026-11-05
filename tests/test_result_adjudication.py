"""Explicitly synthetic source chains; private official files are not CI fixtures."""
import json
from copy import deepcopy

import pytest

from betdoctore import result_adjudication as module
from betdoctore.capture_inventory import save
from betdoctore.result_sources import sha256


@pytest.fixture
def chain(tmp_path, monkeypatch):
    key = 'nba:2025-01-01:BOS:MIA'
    evidence = {'url': 'https://www.nba.com/synthetic-fixture',
                'historical_availability_proven': False,
                'source': {'rawHtml': '<p>Synthetic fixture, not an actual result</p>',
                           'metadata': {'sourceURL': 'https://www.nba.com/synthetic-fixture',
                                        'statusCode': 200}}}
    evidence_path = tmp_path / save(tmp_path, 'synthetic-evidence.json', evidence)
    decision = {
        'scope': 'PRIVATE_NONCOMMERCIAL_GROUND_TRUTH_ADJUDICATION_ONLY',
        'decision_date': '2026-11-05', 'decisions': [{
            'game_key': key, 'points_a': 110, 'points_b': 100, 'team_order': ['BOS', 'MIA'],
            'evidence_file': evidence_path.name, 'evidence_sha256': sha256(evidence_path.read_bytes()),
            'source_url': evidence['url'], 'evidence_grade': 'SYNTHETIC_TEST_ONLY',
            'historical_t60_availability_proven': False,
            'historical_feature_replacement_authorized': False,
            'rejected_score_variants': [{'points_a': 109, 'points_b': 100}],
        }]}
    decision_path = tmp_path / save(tmp_path, 'synthetic-decision.json', decision)
    monkeypatch.setattr(module, 'APPROVED_DECISION_SHA256', sha256(decision_path.read_bytes()))
    original = {'game_key': key, 'phase': 'regular_season', 'reasons': ['SCORE_CONFLICT'],
                'result_consistency_passed': False, 'designated_home': 'BOS', 'observations': [
                    {'source': 'neil-paine-nba-elo', 'points_a': 110, 'points_b': 100,
                     'designated_home': 'BOS'},
                    {'source': 'fixturedownload-private', 'points_a': 109, 'points_b': 100,
                     'designated_home': 'BOS'}]}
    manifest = {'use_scope': 'private_noncommercial', 'source_observations_rewritten': False,
                'games': [original]}
    manifest_path = tmp_path / save(tmp_path, 'synthetic-manifest.json', manifest)

    def verify(actual, keys, root):
        assert keys == {key}
        assert actual['games'][0]['result_consistency_passed'] is False
        return [{'synthetic': True, 'verification': 'TEST_DOUBLE_NOT_REAL_BYTE_PROOF'}]

    monkeypatch.setattr(module, 'verify_outcome_sources', verify)
    return manifest_path, decision_path, tmp_path, tmp_path / 'synthetic-results'


def test_layer_preserves_dissent_and_reverifies_before_read(chain, tmp_path):
    manifest = chain[0]
    original = manifest.read_bytes()
    layer_path = module.persist_layer(*chain, tmp_path / 'layers')
    layer = module.load_layer(layer_path, *chain)
    assert manifest.read_bytes() == original
    entry = layer['games'][0]
    assert entry['original_entry'] == json.loads(original)['games'][0]
    assert entry['original_entry']['result_consistency_passed'] is False
    assert len(entry['dissenting_observation_references']) == 1
    assert len(entry['accepted_observation_references']) == 1
    assert module.ground_truth(layer, entry['game_key'])['points_a'] == 110
    assert layer['production_ready'] is False
    assert layer['historical_features_modified'] is False
    with pytest.raises(ValueError, match='historical feature'):
        module.ground_truth(layer, entry['game_key'], purpose='historical_feature')
    assert module.persist_layer(*chain, tmp_path / 'layers') == layer_path


def test_decision_and_official_content_tampering_rejected(chain):
    _manifest, decision, evidence, _root = chain
    payload = json.loads(decision.read_bytes())
    source = evidence / payload['decisions'][0]['evidence_file']
    source.write_bytes(source.read_bytes() + b' ')
    with pytest.raises(ValueError, match='digest'):
        module.build_layer(*chain)
    decision.write_bytes(decision.read_bytes() + b' ')
    with pytest.raises(ValueError, match='digest'):
        module.build_layer(*chain)


@pytest.mark.parametrize('change', ['identity', 'duplicate', 'accepted', 'dissent'])
def test_unreviewed_manifest_changes_fail_closed(chain, change):
    manifest = chain[0]
    payload = json.loads(manifest.read_bytes())
    entry = payload['games'][0]
    if change == 'identity':
        entry['reasons'].append('HOME_CONFLICT')
    elif change == 'duplicate':
        payload['games'].append(deepcopy(entry))
    elif change == 'accepted':
        entry['observations'][0]['points_a'] += 1
    else:
        entry['observations'][1]['points_b'] += 1
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        module.build_layer(*chain)


def test_stored_layer_is_not_a_self_asserted_proof(chain, tmp_path):
    path = module.persist_layer(*chain, tmp_path / 'layers')
    payload = json.loads(path.read_bytes())
    payload['games'][0]['points_a'] = 999
    forged = path.parent / save(path.parent, 'adjudication-layer.json', payload)
    with pytest.raises(ValueError, match='differs'):
        module.load_layer(forged, *chain)


def test_original_source_verifier_failure_is_propagated(chain, monkeypatch):
    def failed(*args):
        raise ValueError('Synthetic original byte mismatch')
    monkeypatch.setattr(module, 'verify_outcome_sources', failed)
    with pytest.raises(ValueError, match='original byte mismatch'):
        module.build_layer(*chain)
