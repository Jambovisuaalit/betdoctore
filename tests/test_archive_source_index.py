"""Synthetic no-outcome NBA/ESPN archive-index tests."""
from datetime import UTC, datetime

import httpx
import pytest

from betdoctore import archive_source_index as m


def inventory():
    return {"captures":[{"candidate_fixtures":[
        ["2024-03-15T00:30:00+00:00","Boston Celtics","Miami Heat"],
        ["2025-03-15T00:30:00+00:00","Boston Celtics","Miami Heat"]]}]}


def archived(original, stamp="20240313120000", digest="A"*20):
    return {"original":original,"timestamp":stamp,"statuscode":"200",
            "mimetype":"application/json","digest":digest}


def test_no_content_requests_and_zero_admissions(tmp_path):
    called=[]
    def respond(request):
        called.append(request)
        assert request.url.host=="web.archive.org"
        assert "collapse=" not in str(request.url)
        assert "matchType=exact" in str(request.url)
        return httpx.Response(200,json=[[
            "timestamp","original","statuscode","mimetype","digest"]])
    path=tmp_path/"inventory.json"
    path.write_text("{}")
    # Use a mocked validated snapshot, without public source data.
    original=m._snapshot
    m._snapshot=lambda _:inventory()
    try:
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            result=m.run(path,tmp_path/"out",client)
    finally:
        m._snapshot=original
    assert len(called)==5
    assert result["target_candidates"]==2
    assert result["source_admitted_games"]==0
    assert result["payloads_fetched"] is False
    assert result["target_scores_read"] is False


def test_timestamp_and_date_boundaries():
    sources={x[0]:[] for x in m.SOURCES}
    sources["nba-season-2023"]=[
        {"timestamp":"20240313120000","captured_at":"2024-03-13T12:00:00+00:00",
         "cdx_digest":"A"*20,"original":m.SOURCES[0][2],"payload_verified":False}]
    output=m.preview(inventory(),sources)
    assert output["targets_with_index_candidate"]==1
    assert output["source_admitted_games"]==0
    assert output["cases"][0]["sources"][0]["status"]=="TIMESTAMP_CANDIDATE_ONLY"


def test_403_is_unknown_not_zero():
    url=m.SOURCES[0][2]
    with httpx.Client(transport=httpx.MockTransport(
        lambda r:httpx.Response(403))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            m.fetch_index(client,url,datetime(2024,3,1,tzinfo=UTC),
                          datetime(2024,3,15,tzinfo=UTC))


def test_archive_origin_query_is_exact():
    one=m.SOURCES[3][2]
    assert m.canonical(one)==m.canonical(one.replace("https://","http://"))
    assert m.canonical(one)!=m.canonical(one.replace("limit=500","limit=501"))
    assert m.relevant(m.fixtures(inventory())[0],2023,None)
    assert not m.relevant(m.fixtures(inventory())[1],2023,None)
