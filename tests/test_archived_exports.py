"""Synthetic archive fixtures only; no test output is real source evidence."""
import base64
import hashlib
import html
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from betdoctore.archived_exports import (
    acquire_export,
    discover_exports,
    history_capacity,
    load_export,
    parse_export,
)


def fixture(values=None):
    values = values if values is not None else [{
        "MatchNumber": 1, "DateUtc": "2023-12-01T00:00:00Z",
        "HomeTeam": "Boston Celtics", "AwayTeam": "Miami Heat",
        "HomeTeamScore": None, "AwayTeamScore": None}]
    raw = ('<html><textarea>'+html.escape(json.dumps(values))+'</textarea></html>').encode()
    row = {"original": "https://fixturedownload.com/view/json/nba-2023",
           "timestamp": "20231130074258", "statuscode": "200", "mimetype": "text/html",
           "digest": base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")}
    return raw, row, [list(row), list(row.values())]


def test_original_html_verified_before_decoding():
    raw, row, index = fixture()
    result = parse_export(raw, row, index)
    assert result["rows"][0]["game_key"] == "nba:2023-11-30:BOS:MIA"
    assert not result["source_admitted"]
    assert result["rows"][0]["total"] is None
    with pytest.raises(ValueError, match="digest"):
        parse_export(raw+b" ", row, index)
    with pytest.raises(ValueError, match="absent"):
        parse_export(raw, row, [index[0]])
    with pytest.raises(ValueError, match="Unapproved"):
        parse_export(raw, {**row, "original": row["original"]+"?redirect=evil"}, index)


@pytest.mark.parametrize("change", [
    {"HomeTeamScore": 100}, {"HomeTeamScore": True, "AwayTeamScore": 99},
    {"HomeTeamScore": 100, "AwayTeamScore": 100},
    {"HomeTeamScore": 101, "AwayTeamScore": 100},
    {"Winner": "Miami Heat"}, {"DateUtc": "2023-12-01T00:00:00"},
])
def test_invalid_or_future_scores_quarantined(change):
    raw, _, _ = fixture()
    import re
    values = json.loads(html.unescape(re.search(r"<textarea>(.*)</textarea>", raw.decode())[1]))
    raw, row, index = fixture([{**values[0], **change}])
    with pytest.raises(ValueError):
        parse_export(raw, row, index)


def test_no_live_js_fallback_or_ambiguous_textareas():
    for body in (b'<script>fetch("/feed/json/nba-2023")</script>',
                 b'<textarea>[]</textarea><textarea>[]</textarea>'):
        _, row, _ = fixture()
        row["digest"] = base64.b32encode(hashlib.sha1(body).digest()).decode().rstrip("=")
        with pytest.raises(ValueError, match="Exactly one"):
            parse_export(body, row, [list(row), list(row.values())])


def test_acquisition_receipts_revalidate_bytes_terms_and_metadata(tmp_path):
    raw, row, index = fixture()
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=raw))) as client:
        snapshot = acquire_export(tmp_path, row, index, b"synthetic terms", client)
    receipt = tmp_path/snapshot["receipt_path"]
    assert load_export(tmp_path, receipt)["rows"] == snapshot["rows"]
    record = json.loads(receipt.read_text())
    (tmp_path/record["terms_path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="terms"):
        load_export(tmp_path, receipt)


def test_discovery_saves_failure_and_empty_is_not_evidence(tmp_path):
    for status in (200, 503):
        with httpx.Client(transport=httpx.MockTransport(lambda request, status=status: httpx.Response(status, json=[]))) as client:
            report = discover_exports(tmp_path, 2023, client)
        assert (tmp_path/report["receipt_path"]).exists()
        assert ("error" in report) == (status == 503)
    with pytest.raises(ValueError):
        discover_exports(tmp_path, 2021, None)


def capacity_fixture():
    captured = datetime(2023, 11, 30, 7, tzinfo=UTC)
    raw, row, index = fixture()
    rows = parse_export(raw, row, index)["rows"]
    rows[0]["public_available_by"] = captured.isoformat()
    for i in range(5):
        rows.append({**rows[0], "provider_id": f"past:{i}", "game_key": f"past:{i}",
                     "game_date": (captured-timedelta(days=i+1)).date().isoformat(),
                     "total": 210+i, "score_identity": [110, 100+i]})
    return [{"rows": rows}]


def test_capacity_excludes_future_stale_conflicting_and_revised_evidence():
    snapshots = capacity_fixture()
    result = history_capacity(snapshots)
    assert result["fresh_history_capacity_games"] == 1
    assert not result["predictions_frozen"]
    assert result["source_admitted_games"] == 0
    future = json.loads(json.dumps(snapshots))
    for row in future[0]["rows"][1:]:
        row["public_available_by"] = "2023-12-01T00:00:00+00:00"
    assert history_capacity(future)["fresh_history_capacity_games"] == 0
    stale = json.loads(json.dumps(snapshots))
    for row in stale[0]["rows"][1:]:
        row["public_available_by"] = "2023-11-01T00:00:00+00:00"
    assert history_capacity(stale)["fresh_history_capacity_games"] == 0
    conflict = {**snapshots[0]["rows"][1], "score_identity": [111, 100]}
    snapshots.append({"rows": [conflict]})
    assert history_capacity(snapshots)["excluded"][0]["reason"] == "CONFLICTING_CAPTURED_HISTORY"
    snapshots = capacity_fixture()
    snapshots.append({"rows": [{**snapshots[0]["rows"][0], "scheduled_tipoff": "2023-12-01T01:00:00+00:00"}]})
    assert history_capacity(snapshots)["excluded"][0]["reason"] == "TARGET_ALREADY_SCORED_OR_REVISED"


def test_duplicate_game_identities_do_not_inflate_capacity():
    snapshots = capacity_fixture()
    snapshots[0]["rows"].append({**snapshots[0]["rows"][0], "provider_id": "other-provider-id"})
    result = history_capacity(snapshots)
    assert result["candidate_games"] == 1
    assert result["fresh_history_capacity_games"] == 0
    assert {v["reason"] for v in result["excluded"]} == {"AMBIGUOUS_PROVIDER_IDS_FOR_GAME"}


def test_cup_final_is_excluded_without_reading_outcomes():
    snapshots = capacity_fixture()
    snapshots[0]["rows"][0]["game_key"] = "nba:2023-12-09:IND:LAL"
    assert history_capacity(snapshots)["candidate_games"] == 0


def test_feed_and_html_preserve_distinct_original_hashes(tmp_path):
    from betdoctore.archived_exports import load_feed_inventory
    from betdoctore.capture_inventory import save
    from betdoctore.result_sources import sha256
    body, _, _ = fixture()
    import re
    values = json.loads(html.unescape(re.search(r"<textarea>(.*)</textarea>", body.decode())[1]))
    raw = json.dumps(values).encode()
    row = {"original": "https://fixturedownload.com/feed/json/nba-2023",
           "timestamp": "20231130074258", "statuscode": "200", "mimetype": "application/json",
           "digest": base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip("=")}
    index = json.dumps([list(row), list(row.values())]).encode()
    save(tmp_path, "cdx-response", index)
    terms = b"synthetic source terms"
    terms_name = save(tmp_path, "terms.html", terms)
    payload_name = save(tmp_path, "schedule.json", raw)
    captured = "2023-11-30T07:42:58+00:00"
    inventory = {"use_scope": "private_noncommercial", "redistribution_allowed": False,
                 "terms": {"local_path": terms_name, "sha256": sha256(terms)},
                 "captures": [{"cdx": row, "local_path": payload_name,
                               "payload_sha256": sha256(raw), "index_sha256": sha256(index),
                               "retrieved_at": "2026-11-03T00:00:00+00:00",
                               "terms_sha256": sha256(terms),
                               "replay_url": f"https://web.archive.org/web/{row['timestamp']}id_/{row['original']}"}]}
    path = tmp_path/save(tmp_path, "inventory.json", inventory)
    snapshots = load_feed_inventory(tmp_path, path)
    assert snapshots[0]["archive_captured_at"] == captured
    assert snapshots[0]["rows"][0]["snapshot_sha256"] == sha256(raw)
    assert sha256(raw) != sha256(body)
    assert not snapshots[0]["private_terms_verified"]
    (tmp_path/payload_name).write_bytes(raw+b" ")
    with pytest.raises(ValueError, match="SHA-256"):
        load_feed_inventory(tmp_path, path)


def result_fixture(utc=True):
    message = 'Your time zone is not set and will use UTC by default.' if utc else 'Time zone unknown'
    heads = ['Round Number', 'Date', 'Location', 'Home Team', 'Away Team', 'Result']
    content = '<p>'+message+'</p><table><tr>'+''.join(f'<th>{h}</th>' for h in heads)+'</tr>'
    for i in range(5):
        cells = ['1', f'{20+i}/11/2023 20:00', 'Synthetic arena', 'Boston Celtics', 'Miami Heat', '110 - 100']
        content += '<tr>'+''.join(f'<td>{html.escape(c)}</td>' for c in cells)+'</tr>'
    content += '</table>'
    raw = content.encode()
    row = {'original': 'https://fixturedownload.com/results/nba-2023/boston-celtics',
           'timestamp': '20231130074258', 'statuscode': '200', 'mimetype': 'text/html',
           'digest': base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip('=')}
    return raw, row, [list(row), list(row.values())]


def test_result_table_timezone_and_no_invented_provider_ids():
    from betdoctore.archived_exports import parse_results
    raw, row, index = result_fixture()
    snapshot = parse_results(raw, row, index)
    assert all(r['provider_id'] is None and not r['eligible_as_target'] for r in snapshot['rows'])
    assert all(r['total'] == 210 for r in snapshot['rows'])
    assert not snapshot['target_identity_authority']
    raw, row, index = result_fixture(utc=False)
    with pytest.raises(ValueError, match='timezone'):
        parse_results(raw, row, index)


def test_result_history_is_cutoff_bounded_and_never_admitted_implicitly():
    from betdoctore.archived_exports import parse_results
    raw, row, index = fixture()
    target = parse_export(raw, row, index)
    body, metadata, cdx = result_fixture()
    history = parse_results(body, metadata, cdx)
    report = history_capacity([target, history])
    assert report['candidate_games'] == 1
    assert report['fresh_history_capacity_games'] == 1
    assert report['source_admitted_games'] == 0
    for item in history['rows']:
        item['public_available_by'] = '2023-12-01T00:00:00+00:00'
    assert history_capacity([target, history])['fresh_history_capacity_games'] == 0


def test_new_2023_capture_of_2022_23_season_is_distinct_from_development():
    values = [{"MatchNumber": 1, "DateUtc": "2023-03-24T00:00:00Z",
               "HomeTeam": "Boston Celtics", "AwayTeam": "Miami Heat",
               "HomeTeamScore": None, "AwayTeamScore": None}]
    raw, row, _ = fixture(values)
    row.update(original='https://fixturedownload.com/view/json/nba-2022', timestamp='20230323053221')
    index = [list(row), list(row.values())]
    snapshot = parse_export(raw, row, index)
    assert snapshot['rows'][0]['game_date'] == '2023-03-23'
    assert history_capacity([snapshot])['candidate_games'] == 1
    row['timestamp'] = '20221206214536'
    with pytest.raises(ValueError, match='Development-year'):
        parse_export(raw, row, [list(row), list(row.values())])
