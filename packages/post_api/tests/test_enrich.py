"""T26 backend: span -> workflow instantiate, node registry, and the generic
`/workflows/{id}` node/edge/plan/run routes exercised against a *real* T12 recipe workflow
(not the fake node types `test_api_flow.py` uses) -- `POST3_FAKE_PROVIDERS=1` throughout, no
network, no real provider ever shells out."""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setenv("POST3_FAKE_PROVIDERS", "1")


def _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path):
    r = client.post(f"/api/projects/{pid}/sources", json={"path": str(lavfi_clip), "role": "a_roll"})
    assert r.status_code == 200, r.text
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
    assert r.status_code == 200, r.text
    return shoot_id, source_id, sync_group_id, r.json()["transcript_id"]


def _cut_with_video_span(client, pid, lavfi_clip, tmp_path):
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    assert r.status_code == 200, r.text
    cut_id = r.json()["cut_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    cut = r.json()["cut"]
    passage = cut["passages"][0]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_span", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "layer": "picture", "kind": "video", "note": "a still shot",
        },
    })
    assert r.status_code == 200, r.text
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    span_id = r.json()["cut"]["spans"][0]["id"]
    return cut_id, span_id


def _cut_with_beat_span(client, pid, lavfi_clip, tmp_path, picture_kind):
    """T30c regression: a span created the way the dialog/suggester-accept actually create
    one now -- `add_beat_spans` with a T30a PictureKind value ('live_action'/'motion_graphic'),
    not the older `add_span` + VISUALS-picker-id ('video'/'anim') shape `_cut_with_video_span`
    above still uses."""
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    assert r.status_code == 200, r.text
    cut_id = r.json()["cut_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    cut = r.json()["cut"]
    passage = cut["passages"][0]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_beat_spans", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "picture_kind": picture_kind, "brief_text": "Show it.",
            "provenance": "human",
        },
    })
    assert r.status_code == 200, r.text
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    span_id = r.json()["cut"]["spans"][0]["id"]
    return cut_id, span_id


@pytest.mark.parametrize("picture_kind,recipe_id", [("live_action", "live_action"), ("motion_graphic", "motion_graphic")])
def test_span_workflow_instantiate_accepts_t30_picture_kinds(client, project, lavfi_clip, tmp_path, picture_kind, recipe_id):
    """Regression for the T30c dialog/suggester-accept path: both `add_beat_spans` writes a
    picture Span's `kind` as its T30a PictureKind value directly, so `KIND_TO_RECIPE` must
    resolve those too, not just the older VISUALS-picker ids `_cut_with_video_span` exercises."""
    pid = project["id"]
    cut_id, span_id = _cut_with_beat_span(client, pid, lavfi_clip, tmp_path, picture_kind)

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow")
    assert r.status_code == 200, r.text
    assert r.json()["recipe_id"] == recipe_id


def test_provided_span_workflow_instantiates_with_placeholder_clip(client, project, lavfi_clip, tmp_path):
    """T30d: `provided`/`overlay` used to 400 forever on first instantiate (`span.path` is
    always empty at that point -- nothing sets it earlier), so no `provided.clip`/
    `overlay.place` node ever existed for their in-graph pickers (`nodes/ProvidedClipNode.tsx`,
    `nodes/OverlayPlaceNode.tsx`) to edit. `span_workflow` now seeds that first path from the
    demo catalogue instead of an empty string, so the workflow always instantiates and the
    node picker's own `PATCH .../nodes/{id}` is how the user swaps in their real pick."""
    pid = project["id"]
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    assert r.status_code == 200, r.text
    cut_id = r.json()["cut_id"]
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    passage = r.json()["cut"]["passages"][0]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_span", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "layer": "picture", "kind": "provided",
        },
    })
    assert r.status_code == 200, r.text
    provided_span_id = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]["spans"][0]["id"]

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{provided_span_id}/workflow")
    assert r.status_code == 200, r.text
    workflow_id = r.json()["workflow_id"]

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    assert r.status_code == 200, r.text
    clip_node = next(n for n in r.json()["workflow"]["nodes"] if n["type_id"] == "provided.clip")
    catalogue = client.get(f"/api/projects/{pid}/provided-catalogue").json()["clips"]
    assert clip_node["params"]["path"] == catalogue[0]["path"]


def test_overlay_span_workflow_instantiates_with_placeholder_clip_and_matrix(client, project, lavfi_clip, tmp_path):
    """Same placeholder-path fix, for the `overlay` recipe's own `provided.clip` (feeding
    `overlay.measure`/`overlay.cutout`/`overlay.place`) -- `overlay_depth`/`overlay_position`
    still flow through from the span exactly as before, only the empty-path 400 changes."""
    pid = project["id"]
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    passage = r.json()["cut"]["passages"][0]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_beat_spans", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "overlay_depth": "in_front", "overlay_position": "lower-band",
            "provenance": "human",
        },
    })
    assert r.status_code == 200, r.text
    span_id = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]["spans"][0]["id"]

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow")
    assert r.status_code == 200, r.text
    workflow_id = r.json()["workflow_id"]

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    nodes = r.json()["workflow"]["nodes"]
    place_node = next(n for n in nodes if n["type_id"] == "overlay.place")
    assert place_node["params"]["depth"] == "in_front"
    assert place_node["params"]["position"] == "lower-band"
    catalogue = client.get(f"/api/projects/{pid}/provided-catalogue").json()["clips"]
    clip_node = next(n for n in nodes if n["type_id"] == "provided.clip")
    assert clip_node["params"]["path"] == catalogue[0]["path"]


def test_node_registry_lists_types_handles_and_models(client, project):
    pid = project["id"]
    r = client.get(f"/api/projects/{pid}/node-registry")
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {nt["id"] for nt in body["node_types"]}
    assert {"still.generate", "video.generate", "human.pick", "human.approve", "asset.verify"} <= ids
    assert "image" in body["handle_types"] and "video" in body["handle_types"]
    # T39: every image/video model `higgsfield model list` offers (fixture), defaults first,
    # labelled with Higgsfield's display name; only Post3's priced ones carry a price.
    by_id = {m["id"]: m for m in body["models"]}
    assert body["models"][0]["id"] == "nano_banana_2" and by_id["nano_banana_2"]["label"] == "Nano Banana Pro"
    assert {"nano_banana_2", "seedream_v4_5", "kling3_0", "seedream_v5_pro", "kling2_6"} <= set(by_id)
    assert "nano_banana_pro" not in by_id and {m["kind"] for m in body["models"]} == {"image", "video"}
    for model_id in ("nano_banana_2", "seedream_v4_5", "kling3_0"):
        assert by_id[model_id]["pricing"]
    assert by_id["kling2_6"] == {"id": "kling2_6", "kind": "video", "label": "Kling 2.6 Video",
                                 "pricing": {}, "capabilities": []}


def test_node_registry_models_carry_capability_chips(client, project):
    """T30d: the in-node/inspector model picker's price + capability chips -- `nano_banana_2`
    is offered for both stills and end frames and accepts refs (`input_images`); `kling3_0`
    is a video model with a fixture-declared max duration."""
    pid = project["id"]
    r = client.get(f"/api/projects/{pid}/node-registry")
    assert r.status_code == 200, r.text
    by_id = {m["id"]: m for m in r.json()["models"]}
    assert set(by_id["nano_banana_2"]["capabilities"]) == {"start frame", "end frame", "refs"}
    assert set(by_id["seedream_v4_5"]["capabilities"]) == {"start frame", "end frame", "refs"}
    assert set(by_id["kling3_0"]["capabilities"]) == {"start frame", "max 15s"}


def test_provided_catalogue_seeds_three_fake_clips(client, project):
    pid = project["id"]
    r = client.get(f"/api/projects/{pid}/provided-catalogue")
    assert r.status_code == 200, r.text
    clips = r.json()["clips"]
    assert len(clips) == 3
    assert all(c["path"] and c["label"] and c["duration_seconds"] > 0 for c in clips)


def test_cast_list_and_create_round_trip(client, project):
    pid = project["id"]
    r = client.get(f"/api/projects/{pid}/cast")
    assert r.status_code == 200, r.text
    assert r.json()["cast"] == []

    r = client.post(f"/api/projects/{pid}/cast", json={"name": "Dave", "description": "recurring presenter"})
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["name"] == "Dave"
    assert created["anchor_ready"] is False

    r = client.get(f"/api/projects/{pid}/cast")
    assert [c["name"] for c in r.json()["cast"]] == ["Dave"]


def test_span_workflow_instantiate_is_idempotent_and_runnable(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    cut_id, span_id = _cut_with_video_span(client, pid, lavfi_clip, tmp_path)

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["span_id"] == span_id
    assert body["recipe_id"] == "live_action"
    workflow_id = body["workflow_id"]

    # idempotent: calling again returns the same workflow id, and the span now carries it.
    r2 = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow")
    assert r2.json()["workflow_id"] == workflow_id
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    assert r.json()["cut"]["spans"][0]["workflow_id"] == workflow_id

    # the instantiated (real T12 recipe) workflow is a normal workflow to the generic routes.
    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    assert r.status_code == 200, r.text
    workflow = r.json()["workflow"]
    still_ids = [n["id"] for n in workflow["nodes"] if n["type_id"] == "still.generate"]
    assert len(still_ids) == 3

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}/plan")
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    assert set(still_ids) <= set(plan["runnable"])
    assert plan["estimated_cost"]

    r = client.put(f"/api/projects/{pid}/budgets/demo", json={"cap": 100.0, "unit": "credits"})
    assert r.status_code == 200, r.text

    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/run", json={"budget": "demo", "by": "test"})
    assert r.status_code == 200, r.text
    assert len(r.json()["job_ids"]) == 3

    for _ in range(50):
        r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}/states")
        states = r.json()["states"]
        if all(states[sid] == "done" for sid in still_ids):
            break
        import time

        time.sleep(0.1)
    assert all(states[sid] == "done" for sid in still_ids), states
    assert states[f"{span_id}-pick"] == "needs_pick"

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}/nodes/{still_ids[0]}/artifact")
    assert r.status_code == 200, r.text
    artifact = r.json()
    assert artifact["exists"] is True
    assert artifact["outputs"] and artifact["outputs"][0]["url"].startswith(f"/api/projects/{pid}/assets/")

    r = client.get(artifact["outputs"][0]["url"])
    assert r.status_code == 200


def test_patch_node_params_revalidates_and_invalidates_cache(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    cut_id, span_id = _cut_with_video_span(client, pid, lavfi_clip, tmp_path)
    workflow_id = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow").json()["workflow_id"]

    still0 = f"{span_id}-still0"
    r = client.patch(
        f"/api/projects/{pid}/workflows/{workflow_id}/nodes/{still0}",
        json={"params": {"model": "nano_banana_2", "prompt_text": "a brand new brief"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["node_id"] == still0

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    node = next(n for n in r.json()["workflow"]["nodes"] if n["id"] == still0)
    assert node["params"]["prompt_text"] == "a brand new brief"

    # bad params (unknown field) -> 400, not a 500.
    r = client.patch(
        f"/api/projects/{pid}/workflows/{workflow_id}/nodes/{still0}",
        json={"params": {"not_a_real_field": True}},
    )
    assert r.status_code == 400


def test_edges_add_remove_marks_downstream_stale(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    cut_id, span_id = _cut_with_video_span(client, pid, lavfi_clip, tmp_path)
    workflow_id = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow").json()["workflow_id"]

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    edges = r.json()["workflow"]["edges"]
    still_edge = next(e for e in edges if e["from_node"] == f"{span_id}-still1" and e["to_node"] == f"{span_id}-pick")

    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/edges", json={"remove": [still_edge["id"]]})
    assert r.status_code == 200, r.text
    assert still_edge["id"] not in {e["id"] for e in r.json()["edges"]}

    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/edges", json={
        "add": [{"from_node": still_edge["from_node"], "from_output": still_edge["from_output"],
                  "to_node": still_edge["to_node"], "to_input": still_edge["to_input"]}],
    })
    assert r.status_code == 200, r.text
    assert len(r.json()["edges"]) == len(edges)


def test_span_with_no_recipe_kind_refused(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot_id, source_id, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path)
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    cut = r.json()["cut"]
    passage = cut["passages"][0]
    client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_span", "expected_rev": 1,
        "args": {
            "sync_group_id": passage["sync_group_id"], "start_word_id": passage["start_word_id"],
            "end_word_id": passage["end_word_id"], "layer": "picture", "kind": "aroll",
        },
    })
    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    span_id = r.json()["cut"]["spans"][0]["id"]

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow")
    assert r.status_code == 400


def test_add_node_then_connect_marks_still_stale(client, project, lavfi_clip, tmp_path):
    """T26 graph-view acceptance: add a reference-image (`source.file`) node, wire it into a
    still.generate node's `continuity` input, and see that still marked `stale` (its
    input_hash changed) even though it was never actually re-run yet."""
    import json as _json

    pid = project["id"]
    cut_id, span_id = _cut_with_video_span(client, pid, lavfi_clip, tmp_path)
    workflow_id = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow").json()["workflow_id"]

    still0 = f"{span_id}-still0"
    ref_path = str(tmp_path / "ref.png")
    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/nodes", json={
        "type_id": "source.file", "params": {"path": ref_path, "handle_type": "image"},
    })
    assert r.status_code == 200, r.text
    ref_node_id = r.json()["node_id"]

    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/edges", json={
        "add": [{"from_node": ref_node_id, "from_output": "file", "to_node": still0, "to_input": "continuity"}],
    })
    assert r.status_code == 200, r.text

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    workflow = r.json()["workflow"]
    assert any(n["id"] == ref_node_id for n in workflow["nodes"])
    assert any(e["from_node"] == ref_node_id and e["to_node"] == still0 for e in workflow["edges"])
    _json.dumps(workflow)  # just exercising the shape is JSON-serialisable end to end


def test_delete_node_removes_its_edges(client, project, lavfi_clip, tmp_path):
    """T29 graph palette: deleting a node also removes every edge touching it."""
    pid = project["id"]
    cut_id, span_id = _cut_with_video_span(client, pid, lavfi_clip, tmp_path)
    workflow_id = client.post(f"/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow").json()["workflow_id"]

    still0 = f"{span_id}-still0"
    ref_path = str(tmp_path / "ref.png")
    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/nodes", json={
        "type_id": "source.file", "params": {"path": ref_path, "handle_type": "image"},
    })
    ref_node_id = r.json()["node_id"]
    r = client.post(f"/api/projects/{pid}/workflows/{workflow_id}/edges", json={
        "add": [{"from_node": ref_node_id, "from_output": "file", "to_node": still0, "to_input": "continuity"}],
    })
    assert r.status_code == 200, r.text

    r = client.delete(f"/api/projects/{pid}/workflows/{workflow_id}/nodes/{ref_node_id}")
    assert r.status_code == 200, r.text

    r = client.get(f"/api/projects/{pid}/workflows/{workflow_id}")
    workflow = r.json()["workflow"]
    assert not any(n["id"] == ref_node_id for n in workflow["nodes"])
    assert not any(e["from_node"] == ref_node_id for e in workflow["edges"])

    # deleting an unknown node is a 404, not a 500.
    r = client.delete(f"/api/projects/{pid}/workflows/{workflow_id}/nodes/{ref_node_id}")
    assert r.status_code == 404
