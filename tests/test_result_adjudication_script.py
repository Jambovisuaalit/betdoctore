"""Synthetic integrity tests; no claim of historical availability."""
import hashlib
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'adjudicate', Path(__file__).resolve().parents[1] / 'scripts/adjudicate_result_conflicts.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_verified_json_rejects_changed_evidence(tmp_path):
    evidence = tmp_path / 'synthetic.json'
    original = b'{"synthetic": true}'
    digest = hashlib.sha256(original).hexdigest()
    evidence.write_bytes(original)
    assert MODULE.verified_json(evidence, digest) == {'synthetic': True}
    evidence.write_bytes(b'{"synthetic": false}')
    with pytest.raises(ValueError, match='digest mismatch'):
        MODULE.verified_json(evidence, digest)


def test_missing_private_evidence_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError):
        MODULE.decide(tmp_path, tmp_path)
