"""T13b API: `/api/projects/{pid}/cuts/{cut_id}/suggested-visuals` -- suggest (whole cut /
selection), list, accept, dismiss, accept-all. `POST3_FAKE_PROVIDERS=1` throughout so the
demo `DeterministicSuggester` runs (no terminal agent, no network). Builds its project directly
on disk via `post_core.store` (a `kind="virtual"` source, like the T24 script demo) rather
than through the media-ingest HTTP routes, which need real footage."""
from __future__ import annotations

from pathlib import Path

import pytest

from post_core.edit import ops
from post_core.model.common import Rational
from post_core.model.shoot import Shoot, Source, SyncGroup
from post_core.model.transcript import Transcript, Word
from post_core.store import store as store_module

FPS = Rational(num=24000, den=1001)
ASPECT = "16:9"

LONG_SCRIPT = (
    "We reviewed one thousand automation case studies about scheduling systems "
    "carefully before writing anything down today. Then we tested every workflow "
    "against real customer support tickets to see what actually mattered here."
)


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


def _build_project(root: Path) -> dict:
    store_module.init_project(root)
    source = Source(path=None, fps=FPS, role="a_roll", kind="virtual", content_fingerprint="virtual")
    sync_group = SyncGroup(id="sg1", source_ids=[source.id], offsets={source.id: 0.0})
    shoot = Shoot(name="script", sources=[source], sync_groups=[sync_group])
    store_module.write(root, "shoot", shoot, expected_rev=0)

    words = []
    t = 0.0
    for w in LONG_SCRIPT.split():
        words.append(Word(text=w, start=t, end=t + 0.3))
        t += 0.4
    transcript = Transcript(sync_group_id=sync_group.id, provider="synthetic", words=words, fingerprint="fp")
    store_module.write(root, "transcript", transcript, expected_rev=0)

    cut = ops.cut_from_transcript(transcript, source.id, Rational(num=16, den=9))
    store_module.write(root, "cut", cut, expected_rev=0)
    return {"source_id": source.id, "sync_group_id": sync_group.id, "transcript_id": transcript.id, "cut_id": cut.id}


@pytest.fixture
def scene(client, project, tmp_path):
    pid = project["id"]
    ids = _build_project(Path(project["root"]))
    return {"pid": pid, **ids}


def test_suggest_visuals_whole_cut_returns_proposals(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) >= 1
    for item in items:
        assert item["medium"] is not None or item["overlay_depth"] is not None
        if item["medium"] is not None:
            assert item["medium"] in ("aroll", "provided", "live_action", "motion_graphic")
        assert item["brief"]
        assert item["rationale"]
        assert item["transcript_id"] == scene["transcript_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals")
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == len(items)


def test_suggest_visuals_rerun_does_not_duplicate(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    first = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"}).json()["items"]
    second = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"}).json()["items"]
    assert len(second) == len(first)


def test_accept_suggestion_creates_span(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    items = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"}).json()["items"]
    suggestion_id = items[0]["id"]

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/{suggestion_id}/accept")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cut_id"] == cut_id
    assert body["span_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    cut = r.json()["cut"]
    span = next(s for s in cut["spans"] if s["id"] == body["span_id"])
    assert span["provenance"] == "agent"
    if items[0]["medium"] is not None:
        assert span["kind"] == items[0]["medium"]
    else:
        assert span["kind"] == "overlay"
    assert span["brief"]["text"] == items[0]["brief"]

    remaining = client.get(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals").json()["items"]
    assert suggestion_id not in {i["id"] for i in remaining}


def test_accept_unknown_suggestion_400(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/not-an-id/accept")
    assert r.status_code == 400


def test_dismiss_then_resuggest_does_not_bring_it_back(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    items = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"}).json()["items"]
    suggestion_id = items[0]["id"]
    dismissed_range = (items[0]["start_word_id"], items[0]["end_word_id"])

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/{suggestion_id}/dismiss")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == suggestion_id

    again = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"}).json()["items"]
    assert dismissed_range not in {(i["start_word_id"], i["end_word_id"]) for i in again}


def test_accept_all_reports_accepted_count(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    items = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"}).json()["items"]
    assert len(items) >= 1

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals/accept-all")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["accepted"]) == len(items)
    assert body["blocked"] == []

    remaining = client.get(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals").json()["items"]
    assert remaining == []


def test_suggest_selection_scope_out_of_range_is_empty(client, scene):
    pid, cut_id, sg = scene["pid"], scene["cut_id"], scene["sync_group_id"]
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    passage = r.json()["cut"]["passages"][0]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={
        "scope": "selection", "sync_group_id": sg,
        "start_word_id": passage["start_word_id"], "end_word_id": passage["start_word_id"],
    })
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []  # a one-word selection is too short for the demo suggester


def test_suggest_selection_missing_range_400(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "selection"})
    assert r.status_code == 400


def test_real_mode_agent_failure_is_a_502_with_its_reason_and_applies_nothing(client, scene, monkeypatch):
    """T36: real mode asks the terminal agent; the suite points both CLIs at a path that does
    not exist (conftest), so the route reports `not_found` -- no real `claude`/`codex` runs."""
    pid, cut_id = scene["pid"], scene["cut_id"]
    monkeypatch.delenv("POST3_FAKE_PROVIDERS")
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"})
    assert r.status_code == 502, r.text
    assert r.json()["reason"] == "not_found"
    assert "claude CLI not found" in r.json()["error"]
    assert client.get(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals").json()["items"] == []


def test_patch_suggestion_edits_persist_and_carry_into_accept(client, scene):
    """T40: brief / direction note / medium edited on the proposed card persist on the
    suggestion, and accepting it lands the edited values on the real span."""
    pid, cut_id = scene["pid"], scene["cut_id"]
    items = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"}).json()["items"]
    target = next(i for i in items if i["overlay_depth"] is None) if any(i["overlay_depth"] is None for i in items) else items[0]
    sid = target["id"]
    base = f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals"

    r = client.patch(f"{base}/{sid}", json={"brief": "A hand circling a date.", "direction_note": "Slow push in", "medium": "motion_graphic"})
    assert r.status_code == 200, r.text
    assert r.json()["brief"] == "A hand circling a date."
    assert r.json()["direction_note"] == "Slow push in"
    assert r.json()["medium"] == "motion_graphic"
    assert r.json()["rationale"] == target["rationale"]

    listed = {i["id"]: i for i in client.get(base).json()["items"]}
    assert listed[sid]["brief"] == "A hand circling a date."

    # Only the fields sent change.
    r = client.patch(f"{base}/{sid}", json={"direction_note": "Hold still"})
    assert r.json()["brief"] == "A hand circling a date."
    assert r.json()["direction_note"] == "Hold still"

    assert client.post(f"{base}/{sid}/accept").status_code == 200
    cut = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]
    picture = next(s for s in cut["spans"] if s["layer"] == "picture" and s["start_anchor"]["word_id"] == target["start_word_id"])
    assert picture["kind"] == "motion_graphic"
    assert picture["brief"]["text"] == "A hand circling a date."
    assert picture["direction_note"] == "Hold still"


def test_patch_suggestion_refuses_bad_edits(client, scene):
    pid, cut_id = scene["pid"], scene["cut_id"]
    items = client.post(f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals", json={"scope": "cut"}).json()["items"]
    base = f"/api/projects/{pid}/cuts/{cut_id}/suggested-visuals"
    assert client.patch(f"{base}/not-an-id", json={"brief": "x"}).status_code == 400
    assert client.patch(f"{base}/{items[0]['id']}", json={"medium": "hologram"}).status_code == 422
    assert client.patch(f"{base}/{items[0]['id']}", json={"rationale": "mine"}).status_code == 422
    assert client.patch(f"{base}/{items[0]['id']}", json={"brief": None}).status_code == 400
    no_overlay = [i for i in items if i["overlay_depth"] is None]
    if no_overlay:
        # Overlay-only needs an overlay; with none, the edit is refused and nothing changes.
        sid = no_overlay[0]["id"]
        assert client.patch(f"{base}/{sid}", json={"medium": None}).status_code == 400
        after = {i["id"]: i for i in client.get(base).json()["items"]}
        assert after[sid]["medium"] == no_overlay[0]["medium"]
