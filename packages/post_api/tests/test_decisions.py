"""T30b API: `/api/projects/{pid}/cuts/{cut_id}/decisions` -- pick/approve/waiting_on rows
derived from a cut's spans and their instantiated workflows' graph states."""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


def _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path):
    r = client.post(f"/api/projects/{pid}/sources", json={"path": str(lavfi_clip), "role": "a_roll"})
    body = r.json()
    shoot_id, source_id, sync_group_id = body["shoot_id"], body["source_id"], body["sync_group_id"]

    transcript_path = tmp_path / "t.json"
    transcript_path.write_text(json.dumps([
        {"text": "hello", "start": 0.0, "end": 0.4},
        {"text": "there", "start": 0.4, "end": 0.8},
        {"text": "world", "start": 0.8, "end": 1.4},
    ]))
    r = client.post(f"/api/projects/{pid}/ingest/import-transcript", json={
        "shoot": shoot_id, "sync_group": sync_group_id, "path": str(transcript_path), "format": "json",
    })
    return shoot_id, source_id, sync_group_id, r.json()["transcript_id"]


def test_decisions_lists_pick_row_for_an_instantiated_live_action_span(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    passage = r.json()["cut"]["passages"][0]
    client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_span", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "layer": "picture", "kind": "video",
        },
    })
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    span_id = r.json()["cut"]["spans"][0]["id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}/decisions")
    assert r.status_code == 200, r.text
    assert r.json() == {"rows": [], "counts": {"pick": 0, "approve": 0, "failed": 0, "waiting_on": 0}}

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow")
    assert r.status_code == 200, r.text

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}/decisions")
    assert r.status_code == 200, r.text
    body = r.json()
    pick_rows = [row for row in body["rows"] if row["kind"] == "pick"]
    assert len(pick_rows) == 1
    assert pick_rows[0]["span_id"] == span_id
    assert pick_rows[0]["node_id"] == f"{span_id}-pick"
    assert body["counts"]["pick"] == 1


def test_more_variants_grows_the_pick_options(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    passage = r.json()["cut"]["passages"][0]
    client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_span", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "layer": "picture", "kind": "video",
        },
    })
    span_id = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]["spans"][0]["id"]
    workflow_id = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow").json()["workflow_id"]

    before = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    before_stills = [n for n in before.json()["workflow"]["nodes"] if n["type_id"] == "still.generate"]

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow/more-variants", json={"count": 3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["node_ids"]) == 3

    after = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    after_stills = [n for n in after.json()["workflow"]["nodes"] if n["type_id"] == "still.generate"]
    assert len(after_stills) == len(before_stills) + 3

    options = [e for e in after.json()["workflow"]["edges"] if e["to_node"] == f"{span_id}-pick"]
    assert len(options) == len(after_stills)


def test_more_variants_without_a_workflow_is_400(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    passage = r.json()["cut"]["passages"][0]
    client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_span", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "layer": "picture", "kind": "video",
        },
    })
    span_id = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]["spans"][0]["id"]

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow/more-variants", json={"count": 3})
    assert r.status_code == 400
