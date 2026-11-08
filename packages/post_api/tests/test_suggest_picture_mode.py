"""T42 API: the project's picture mode (`PATCH /api/projects/{pid}`), an audio-only Suggest run
covering every word, re-running replacing rather than stacking, and switching a proposal's
variant. `POST3_FAKE_PROVIDERS=1`: the demo suggester runs, never a terminal agent."""
from __future__ import annotations

from pathlib import Path

import pytest

from post_core.edit.suggest_models import Suggestion, SuggestionVariant
from post_core.edit.suggest_store import update_suggestions
from post_core.model.common import WordAnchor
from post_core.store import store as store_module

from .test_suggest import _build_project


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


@pytest.fixture
def scene(client, project):
    return {"pid": project["id"], "root": Path(project["root"]), **_build_project(Path(project["root"]))}


def test_patch_picture_mode(client, scene):
    pid = scene["pid"]
    assert client.get(f"/api/projects/{pid}").json()["picture_mode"] == "presenter"
    r = client.patch(f"/api/projects/{pid}", json={"picture_mode": "audio_only"})
    assert r.status_code == 200, r.text
    assert r.json()["picture_mode"] == "audio_only"
    assert client.patch(f"/api/projects/{pid}", json={"picture_mode": "radio"}).status_code == 422


def test_audio_only_run_covers_every_word_and_reruns_replace(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    client.patch(f"/api/projects/{pid}", json={"picture_mode": "audio_only"})
    base = f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals"
    words = [w.id for w in store_module.read(scene["root"], "transcript", scene["transcript_id"])[0].words]
    for _ in range(2):
        items = client.post(base, json={"scope": "cut"}).json()["items"]
        ranges = sorted((words.index(i["start_word_id"]), words.index(i["end_word_id"])) for i in items)
        assert ranges[0][0] == 0 and ranges[-1][1] == len(words) - 1
        assert all(b[0] == a[1] + 1 for a, b in zip(ranges, ranges[1:])), ranges  # contiguous, no overlap
        assert all(i["medium"] not in (None, "aroll") for i in items)


def test_switch_variant(client, scene):
    pid, cut_id, root = scene["pid"], scene["cut_id"], scene["root"]
    words = store_module.read(root, "transcript", scene["transcript_id"])[0].words
    anchor = lambda w: WordAnchor(transcript_id=scene["transcript_id"], word_id=w.id)  # noqa: E731
    ideas = [SuggestionVariant(medium="live_action", brief="A city", rationale="a"),
             SuggestionVariant(medium="motion_graphic", brief="A chart", rationale="b")]
    s = Suggestion(start_anchor=anchor(words[0]), end_anchor=anchor(words[3]), **ideas[0].model_dump(), variants=ideas)
    update_suggestions(root, cut_id, lambda f: f.model_copy(update={"items": [s]}))
    base = f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals"
    listed = client.get(base).json()["items"][0]
    assert [v["brief"] for v in listed["variants"]] == ["A city", "A chart"] and listed["active_variant"] == 0
    r = client.post(f"{base}/{s.id}/variant", json={"index": 1})
    assert r.status_code == 200, r.text
    assert (r.json()["brief"], r.json()["medium"], r.json()["active_variant"]) == ("A chart", "motion_graphic", 1)
    assert client.post(f"{base}/{s.id}/variant", json={"index": 7}).status_code == 400
