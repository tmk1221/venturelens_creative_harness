"""T37 through the API: a beat on a 4:5 cut instantiates its recipe for 4:5 -- the video
model's nearest covering aspect plus `crop_to`, verified at the cut's own fps -- and a brief
that asks for a hold relaxes the frozen-tail check."""
from __future__ import annotations

import pytest

from .test_enrich import _build_shoot_and_transcript


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


def _beat_on_cut(client, pid, lavfi_clip, tmp_path, aspect: str, brief: str) -> tuple[str, str]:
    _shoot, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": aspect})
    assert r.status_code == 200, r.text
    cut_id = r.json()["cut_id"]
    passage = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]["passages"][0]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_beat_spans", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "picture_kind": "live_action", "brief_text": brief,
            "provenance": "human",
        },
    })
    assert r.status_code == 200, r.text
    return cut_id, client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]["spans"][0]["id"]


def _nodes(client, pid, cut_id, span_id) -> dict:
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow")
    assert r.status_code == 200, r.text
    wf = client.get(f"/api/projects/{pid}/workflows/{r.json()['workflow_id']}").json()["workflow"]
    return {n["id"]: n["params"] for n in wf["nodes"]}


def test_4x5_cut_beat_generates_for_4x5(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    cut_id, span_id = _beat_on_cut(client, pid, lavfi_clip, tmp_path, "4:5", "A city street at dusk.")
    params = _nodes(client, pid, cut_id, span_id)
    cut = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]
    fps = f"{cut['fps']['num']}/{cut['fps']['den']}"

    video = params[f"{span_id}-video"]
    assert (video["aspect"], video["crop_to"], video["fps"]) == ("9:16", "4:5", fps)
    assert params[f"{span_id}-still0"]["aspect"] == "9:16"
    verify = params[f"{span_id}-verify"]
    assert (verify["expect_aspect"], verify["expect_fps"], verify["allow_hold"]) == ("4:5", fps, False)
    assert verify["min_seconds"] > 0


def test_brief_asking_for_a_hold_allows_one(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    cut_id, span_id = _beat_on_cut(client, pid, lavfi_clip, tmp_path, "9:16", "Push in, then freeze frame on the logo.")
    params = _nodes(client, pid, cut_id, span_id)
    assert params[f"{span_id}-video"]["crop_to"] is None
    assert params[f"{span_id}-verify"]["allow_hold"] is True
