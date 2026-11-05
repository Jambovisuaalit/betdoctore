"""Outcome-blind next-sample capacity gate; no forecasts or outcomes are read."""
import json
from datetime import date
from pathlib import Path

from .archived_exports import history_capacity, load_export
from .result_sources import sha256

EXPOSURE_SHA256 = '092155959d1e45a52ecf3e08c50585ebcb83e9733d67ae8544468d87728b2313'


def capacity_preview(snapshots: list[dict], exposed: set[str], periods: list[dict]) -> dict:
    windows = [(date.fromisoformat(p['start']), date.fromisoformat(p['end'])) for p in periods]
    windows.sort()
    if (len(windows) < 2 or any(a > b or a.year <= 2022 for a, b in windows)
            or any(windows[i][0] <= windows[i-1][1] for i in range(1, len(windows)))):
        raise ValueError('At least two disjoint post-development periods required')
    if not snapshots or not all(s.get('private_terms_verified') is True for s in snapshots):
        raise ValueError('Verified private source terms required for every capture')
    capacity = history_capacity(snapshots)
    selected = [r for r in capacity['candidates_with_history']
                if r['game_key'] not in exposed and any(
                    start.isoformat() <= r['game_key'].split(':')[1] <= end.isoformat()
                    for start, end in windows)]
    support = []
    for start, end in windows:
        days = [date.fromisoformat(r['game_key'].split(':')[1]) for r in selected
                if start.isoformat() <= r['game_key'].split(':')[1] <= end.isoformat()]
        span = (max(days) - min(days)).days + 1 if days else 0
        support.append({'start': start.isoformat(), 'end': end.isoformat(),
                        'capacity_games': len(days), 'observed_span_days': span,
                        'seven_day_block_support': span >= 21})
    return {
        'schema_version': 1, 'status': 'CAPACITY_PREVIEW_ONLY',
        'scope': 'private_noncommercial', 'candidate_games': capacity['candidate_games'],
        'fresh_history_capacity_games': capacity['fresh_history_capacity_games'],
        'unexposed_capacity_games_in_proposed_periods': len(selected),
        'exposed_capacity_games_excluded': sum(r['game_key'] in exposed
                                              for r in capacity['candidates_with_history']),
        'excluded_exposure_registry_games': len(exposed), 'periods': support,
        'planning_capacity_sufficient': len(selected) >= 300 and all(
            r['seven_day_block_support'] for r in support),
        'planning_target_is_significance_guarantee': False,
        'capacity_game_keys': sorted(r['game_key'] for r in selected),
        'source_admitted_games': 0, 'periods_locked': False, 'predictions_frozen': False,
        'current_outcome_manifest_opened': False, 'independent_test_ready': False,
        'production_ready': False,
        'remaining_gates': ['source and definition review', 'historical regular identity',
                            'protocol lock before forecasting', 'post-freeze original outcome verification'],
    }


def inventory_preview(directory: Path, exposure_registry: Path, periods: list[dict]) -> dict:
    raw = exposure_registry.read_bytes()
    if sha256(raw) != EXPOSURE_SHA256:
        raise ValueError('Previously exposed cohort registry changed')
    registry = json.loads(raw)
    if (registry['future_independent_test_reuse_allowed'] is not False
            or registry['scope'] != 'private_noncommercial'):
        raise ValueError('Exposure registry policy mismatch')
    receipts = sorted(directory.glob('*.capture-receipt.json'))
    snapshots = [load_export(directory, p) for p in receipts]
    result = capacity_preview(snapshots, set(registry['exposed_keys']), periods)
    result['exposure_registry_sha256'] = sha256(raw)
    result['capture_receipts'] = {p.name: sha256(p.read_bytes()) for p in receipts}
    return result
