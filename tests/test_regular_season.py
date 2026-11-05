"""Explicit synthetic fixtures for regular-only curation and per-target gates."""
from datetime import UTC, date, datetime

from betdoctore.historical_availability import score_identity
from betdoctore.private_results import NAMES
from betdoctore.regular_season import build_regular_manifest, save_regular_manifest, target_gate
from betdoctore.results import TEAMS, BasicResult


def record(a,b,day=date(2021,1,1),source="neil-paine-nba-elo",points_a=120,points_b=110):
    return BasicResult(source=source,source_snapshot_sha256="a"*64,source_row_numbers=[1],
                       game_key=f"nba:{day}:{a}:{b}",game_date=day,season_end_year=2021,
                       team_a=a,team_b=b,points_a=points_a,points_b=points_b,
                       designated_home=a,neutral=False,phase="non_playoff_unspecified",
                       retrieved_at=datetime(2026,10,27,tzinfo=UTC),
                       available_at=datetime(2026,10,27,tzinfo=UTC))


def season_fixture():
    teams=sorted(TEAMS)
    reverse={v:k for k,v in NAMES.items()}
    records,rows=[],[]
    for a,b in zip(teams[::2],teams[1::2],strict=True):
        r=record(a,b)
        records.extend([r,r.model_copy(update={"source":"fixturedownload-private"})])
        rows.append({"DateUtc":"2021-01-02T00:00:00Z","HomeTeam":reverse[a],"AwayTeam":reverse[b],
                     "HomeTeamScore":120,"AwayTeamScore":110})
    cup=record("ATL","BOS",date(2021,1,3))
    playoff=record("ATL","BOS",date(2021,6,1)).model_copy(update={"phase":"playoffs"})
    playin=record("ATL","BOS",date(2021,5,1))
    rows.append({"DateUtc":"2021-01-04T00:00:00Z","HomeTeam":reverse['ATL'],"AwayTeam":reverse['BOS'],
                 "HomeTeamScore":120,"AwayTeamScore":110})
    records.extend([cup,playoff,playin])
    contract={"seasons":[{"season_end_year":2021,"regular_expected_games":15,"regular_games_per_team":1,
                           "playoff_expected_games":85,"play_in_expected_games":6}],
              "cup_finals":[{"season_end_year":2021,"game_key":cup.game_key}]}
    schedules={2021:{"rows":rows,"manifest":{"retrieved_at":"2026-10-27T00:00:00Z"}}}
    return records,schedules,contract,cup,playoff,playin


def test_regular_scope_excludes_all_non_regular_and_postseason_does_not_block_target(tmp_path):
    records,schedules,contract,cup,playoff,playin=season_fixture()
    manifest=build_regular_manifest(records,schedules,contract,date(2026,10,27))
    assert manifest["regular_catalog_games"]==15
    assert manifest["consistent_result_games"]==15
    keys={g["game_key"] for g in manifest["games"]}
    assert not keys & {cup.game_key,playoff.game_key,playin.game_key}
    assert manifest["work_queues"]["playoffs"][0]["playoff_observed"]==1
    assert manifest["work_queues"]["playoffs"][0]["blocks_regular_v1_cohort"] is False
    assert target_gate(manifest,records[0].game_key)["passed"]
    assert not target_gate(manifest,playoff.game_key)["passed"]
    assert manifest["v1_cohort_policy"]["all_seasons_must_be_complete"] is False
    assert save_regular_manifest(manifest,tmp_path).exists()
    assert list(tmp_path.glob('*.html'))


def test_conflicting_scores_stay_quarantined_despite_one_capture_supported_candidate():
    records,schedules,contract,*_=season_fixture()
    r=records[0]
    records[1]=records[1].model_copy(update={"points_a":121})
    evidence={score_identity(r.game_key,120,110):{"public_available_by":"2021-01-02T00:00:00Z"}}
    manifest=build_regular_manifest(records,schedules,contract,date(2026,10,27),evidence)
    row=next(g for g in manifest['games'] if g['game_key']==r.game_key)
    assert row['points_a'] is None
    assert not row['result_consistency_passed']
    queue=manifest['work_queues']['regular_data_quality'][0]
    assert queue['capture_supported_score_candidate']['points_a']==120
    assert queue['automatic_adjudication_applied'] is False
    assert not target_gate(manifest,r.game_key)['passed']
    assert target_gate(manifest,records[2].game_key)['passed']


def test_opponent_swap_is_flagged_even_if_regular_total_balances():
    records,schedules,contract,*_=season_fixture()
    # In the fixture, swap one team's opponent; retain an archive observation
    # on the same date with the actual participant identity. No repair is inferred.
    original=records[0]
    replacement=record(original.team_a,'CHI',source='fixturedownload-private')
    if replacement.team_a>=replacement.team_b:
        raise AssertionError('test identities must stay sorted')
    rows=schedules[2021]['rows']
    reverse={v:k for k,v in NAMES.items()}
    rows[0]['AwayTeam']=reverse['CHI']
    records[1]=replacement
    manifest=build_regular_manifest(records,schedules,contract,date(2026,10,27))
    row=next(g for g in manifest['games'] if g['game_key']==replacement.game_key)
    assert 'OPPONENT_IDENTITY_CONFLICT' in row['reasons']
    assert not target_gate(manifest,replacement.game_key)['passed']
    queue=next(q for q in manifest['work_queues']['regular_data_quality']
               if q.get('game_key')==replacement.game_key)
    assert queue['replacement_identity_candidates'][0]['record']['game_key']==original.game_key


def test_unrelated_season_missing_catalog_is_a_queue_item_not_target_blocker():
    records,schedules,contract,*_=season_fixture()
    contract['seasons'].append({'season_end_year':2022,'regular_expected_games':1230,
                                'regular_games_per_team':82,'playoff_expected_games':87,'play_in_expected_games':6})
    manifest=build_regular_manifest(records,schedules,contract,date(2026,10,27))
    assert any(q['kind']=='MISSING_REGULAR_CATALOG' for q in manifest['work_queues']['regular_data_quality'])
    assert target_gate(manifest,records[0].game_key)['passed']
