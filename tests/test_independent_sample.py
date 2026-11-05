"""Synthetic outcome-blind sample gates, not actual historical source evidence."""
from datetime import date, timedelta

import pytest

from betdoctore import independent_sample as sample


def test_exposure_and_temporal_support_cannot_be_repaired_by_padding(monkeypatch):
    periods = [{'start': '2025-01-01', 'end': '2025-06-30'},
               {'start': '2026-01-01', 'end': '2026-06-30'}]
    rows = []
    for year in (2025, 2026):
        for n in range(160):
            day = date(year, 2, 1) + timedelta(days=n % 13)
            rows.append({'game_key': f'nba:{day}:SYNTHETIC:{n}'})
    monkeypatch.setattr(sample, 'history_capacity', lambda snapshots: {
        'candidate_games': 320, 'fresh_history_capacity_games': 320,
        'candidates_with_history': rows})
    result = sample.capacity_preview([{'private_terms_verified': True}],
                                     {rows[0]['game_key']}, periods)
    assert result['unexposed_capacity_games_in_proposed_periods'] == 319
    assert result['exposed_capacity_games_excluded'] == 1
    assert result['planning_capacity_sufficient'] is False  # 13 days, despite outer padding.
    assert not result['periods_locked']
    assert result['source_admitted_games'] == 0
    assert rows[0]['game_key'] not in result['capacity_game_keys']


@pytest.mark.parametrize('periods', [
    [{'start': '2022-01-01', 'end': '2022-02-01'},
     {'start': '2023-01-01', 'end': '2023-02-01'}],
    [{'start': '2025-01-01', 'end': '2025-02-01'},
     {'start': '2025-02-01', 'end': '2025-03-01'}],
    [{'start': '2025-01-01', 'end': '2025-02-01'}],
])
def test_invalid_or_development_periods_rejected(periods):
    with pytest.raises(ValueError, match='disjoint post-development'):
        sample.capacity_preview([], set(), periods)


def test_changed_exposure_registry_rejected_before_source_reads(tmp_path):
    path = tmp_path / 'synthetic-registry.json'
    path.write_text('{}')
    with pytest.raises(ValueError, match='registry changed'):
        sample.inventory_preview(tmp_path, path, [])
