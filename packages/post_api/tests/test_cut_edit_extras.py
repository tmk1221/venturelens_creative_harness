"""T11 additive endpoints: cut timeline, swap-candidates, and transcript suggestions."""
from __future__ import annotations

import json


def _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path, words, suffix=""):
    r = client.post(f"/api/projects/{pid}/sources", json={"path": str(lavfi_clip), "role": "a_roll"})
    assert r.status_code == 200, r.text
    body = r.json()
    shoot_id, source_id, sync_group_id = body["shoot_id"], body["source_id"], body["sync_group_id"]

    transcript_path = tmp_path / f"t{suffix}.json"
    transcript_path.write_text(json.dumps(words))
    r = client.post(f"/api/projects/{pid}/ingest/import-transcript", json={
        "shoot": shoot_id, "sync_group": sync_group_id, "path": str(transcript_path), "format": "json",
    })
    assert r.status_code == 200, r.text
    return shoot_id, source_id, sync_group_id, r.json()["transcript_id"]


def _words(texts, step=0.3):
    out = []
    t = 0.0
    for text in texts:
        out.append({"text": text, "start": t, "end": t + step * 0.8})
        t += step
    return out


def test_cut_timeline_returns_ordered_segments(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot, source_id, _sg, transcript_id = _build_shoot_and_transcript(
        client, pid, lavfi_clip, tmp_path, _words(["hello", "there", "world"]),
    )
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    assert r.status_code == 200, r.text
    cut_id = r.json()["cut_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}/timeline")
    assert r.status_code == 200, r.text
    segments = r.json()
    assert len(segments) == 1
    seg = segments[0]
    assert seg["angle_source_id"] == source_id
    assert seg["start_frame"] == 0
    assert seg["duration_frames"] > 0


def test_swap_candidates_finds_similar_take(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot, source_id, sync_group_id, transcript_id = _build_shoot_and_transcript(
        client, pid, lavfi_clip, tmp_path,
        _words(["I", "think", "this", "works", "well", "I", "think", "this", "works", "great"]),
    )
    r = client.get(f"/api/projects/{pid}/transcripts/{transcript_id}/words")
    word_ids = [w["id"] for w in r.json()["words"]]

    r = client.get(f"/api/projects/{pid}/cuts/does-not-exist/swap-candidates", params={
        "sync_group_id": sync_group_id, "start_word_id": word_ids[0], "end_word_id": word_ids[4],
    })
    assert r.status_code == 404

    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}/swap-candidates", params={
        "sync_group_id": sync_group_id, "start_word_id": word_ids[0], "end_word_id": word_ids[4],
    })
    assert r.status_code == 200, r.text
    candidates = r.json()
    assert candidates
    assert candidates[0]["start_word_id"] == word_ids[5]


def test_transcript_suggestions_filler_and_silence(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    words = [
        {"text": "So", "start": 0.0, "end": 0.3},
        {"text": "um", "start": 0.3, "end": 0.5},
        {"text": "hi", "start": 0.5, "end": 0.8},
        {"text": "there", "start": 2.5, "end": 2.8},
    ]
    _shoot, _source, _sg, transcript_id = _build_shoot_and_transcript(client, pid, lavfi_clip, tmp_path, words)

    r = client.get(f"/api/projects/{pid}/transcripts/{transcript_id}/suggestions")
    assert r.status_code == 200, r.text
    kinds = {s["kind"] for s in r.json()}
    assert kinds == {"filler", "silence"}

    r = client.get(f"/api/projects/{pid}/transcripts/{transcript_id}/suggestions", params={"kind": "filler"})
    assert all(s["kind"] == "filler" for s in r.json())


def test_cut_list_returns_master_and_derived(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot, source_id, _sg, transcript_id = _build_shoot_and_transcript(
        client, pid, lavfi_clip, tmp_path, _words(["a", "b", "c", "d"]),
    )
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]

    r = client.get(f"/api/projects/{pid}/cuts")
    assert r.status_code == 200, r.text
    summaries = r.json()
    assert len(summaries) == 1
    assert summaries[0]["id"] == cut_id
    assert summaries[0]["passage_count"] == 1


def test_cut_derive_creates_a_cut_over_a_passage_subset(client, project, lavfi_clip, tmp_path):
    """Regression for T19: `cut_derive` used to pass the raw `{id: Transcript}` dict straight
    into `ops.derive_cut` instead of `.values()`, so `TranscriptIndex` iterated dict keys
    (strings) and blew up with `AttributeError: 'str' object has no attribute
    'sync_group_id'` on every real call -- caught by exercising T19's "derive short from
    selection" against a live post_api server, not by any existing test (this endpoint had
    none)."""
    pid = project["id"]
    _shoot, source_id, _sg, transcript_id = _build_shoot_and_transcript(
        client, pid, lavfi_clip, tmp_path, _words(["a", "b", "c", "d", "e", "f"]),
    )
    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    assert r.status_code == 200, r.text
    parent = r.json()["cut_id"]

    r = client.get(f"/api/projects/{pid}/cuts/{parent}")
    assert r.status_code == 200, r.text
    passage_id = r.json()["cut"]["passages"][0]["id"]

    r = client.post(f"/api/projects/{pid}/cuts/derive", json={
        "parent": parent, "passage_ids": [passage_id], "aspect": "9:16", "variant_label": "short",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_cut_id"] == parent
    derived_id = body["cut_id"]
    assert derived_id != parent

    r = client.get(f"/api/projects/{pid}/cuts/{derived_id}")
    assert r.status_code == 200, r.text
    derived = r.json()["cut"]
    assert derived["parent_cut_id"] == parent
    assert derived["aspect"] == {"num": 9, "den": 16}
    assert derived["variant_label"] == "short"
    assert len(derived["passages"]) == 1

    r = client.get(f"/api/projects/{pid}/cuts")
    assert r.status_code == 200, r.text
    ids = {s["id"] for s in r.json()}
    assert {parent, derived_id} <= ids


def test_list_shoots_resolves_sync_group_to_transcript_and_angle(client, project, lavfi_clip, tmp_path):
    pid = project["id"]
    _shoot, source_id, sync_group_id, transcript_id = _build_shoot_and_transcript(
        client, pid, lavfi_clip, tmp_path, _words(["hello", "there"]),
    )
    r = client.get(f"/api/projects/{pid}/shoots")
    assert r.status_code == 200, r.text
    shoots = r.json()
    assert len(shoots) == 1
    shoot = shoots[0]
    assert transcript_id in shoot["transcript_ids"]
    assert any(s["id"] == source_id for s in shoot["sources"])
    assert any(g["id"] == sync_group_id for g in shoot["sync_groups"])


def test_add_span_and_remove_span_ops(client, project, lavfi_clip, tmp_path):
    """T24: the minimal span ops the raw-transcript 'Add visual' / 'Remove' actions use."""
    pid = project["id"]
    _shoot, source_id, sync_group_id, transcript_id = _build_shoot_and_transcript(
        client, pid, lavfi_clip, tmp_path, _words(["one", "two", "three", "four", "five"]),
    )
    r = client.get(f"/api/projects/{pid}/transcripts/{transcript_id}/words")
    word_ids = [w["id"] for w in r.json()["words"]]

    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]
    starting_rev = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["revision"]

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_span",
        "args": {
            "sync_group_id": sync_group_id, "start_word_id": word_ids[1], "end_word_id": word_ids[2],
            "layer": "picture", "kind": "video", "note": "a detail shot",
        },
        "expected_rev": starting_rev,
    })
    assert r.status_code == 200, r.text
    rev = r.json()["revision"]

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    cut = r.json()["cut"]
    assert len(cut["spans"]) == 1
    span = cut["spans"][0]
    assert span["layer"] == "picture"
    assert span["kind"] == "video"
    assert span["note"] == "a detail shot"
    assert span["start_anchor"]["word_id"] == word_ids[1]
    assert span["end_anchor"]["word_id"] == word_ids[2]

    # overlapping add on the same layer is rejected (spans on the same layer can't overlap)
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_span",
        "args": {
            "sync_group_id": sync_group_id, "start_word_id": word_ids[2], "end_word_id": word_ids[3],
            "layer": "picture", "kind": "anim",
        },
        "expected_rev": rev,
    })
    assert r.status_code == 400, r.text

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "remove_span", "args": {"span_id": span["id"]}, "expected_rev": rev,
    })
    assert r.status_code == 200, r.text

    r = client.get(f"/api/projects/{pid}/cuts/{cut_id}")
    assert r.json()["cut"]["spans"] == []

    # Regression: applying any op writes a `<cut_id>.undo.json` stack file alongside the cut
    # (store/undo.py) -- the cut list must not try to parse that as a Cut.
    r = client.get(f"/api/projects/{pid}/cuts")
    assert r.status_code == 200, r.text
    assert [c["id"] for c in r.json()] == [cut_id]


def test_add_beat_spans_op_creates_both_layers(client, project, lavfi_clip, tmp_path):
    """T30c: the "Add visual" dialog's own op (wired into the generic `/ops` dispatcher
    alongside `add_span`/`remove_span`) -- one atomic call creates a beat's picture AND
    overlay Span together, carrying the full T30 beat model (brief/flags/overlay position)."""
    pid = project["id"]
    _shoot, source_id, sync_group_id, transcript_id = _build_shoot_and_transcript(
        client, pid, lavfi_clip, tmp_path, _words(["one", "two", "three", "four", "five"]),
    )
    word_ids = [w["id"] for w in client.get(f"/api/projects/{pid}/transcripts/{transcript_id}/words").json()["words"]]

    r = client.post(f"/api/projects/{pid}/cuts", json={"transcript": transcript_id, "angle": source_id, "aspect": "16:9"})
    cut_id = r.json()["cut_id"]
    rev = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["revision"]

    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_beat_spans",
        "args": {
            "sync_group_id": sync_group_id, "start_word_id": word_ids[1], "end_word_id": word_ids[2],
            "picture_kind": "live_action", "brief_text": "Show the product.", "direction_note": "handheld",
            "flags": ["must_have_shot"], "overlay_depth": "in_front", "overlay_position": "lower-band",
            "provenance": "human",
        },
        "expected_rev": rev,
    })
    assert r.status_code == 200, r.text

    cut = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["cut"]
    assert len(cut["spans"]) == 2
    picture = next(s for s in cut["spans"] if s["layer"] == "picture")
    overlay = next(s for s in cut["spans"] if s["layer"] == "overlay")
    assert picture["kind"] == "live_action"
    assert picture["brief"]["text"] == "Show the product."
    assert picture["flags"] == ["must_have_shot"]
    assert overlay["overlay_depth"] == "in_front"
    assert overlay["overlay_position"] == "lower-band"
    assert overlay["start_anchor"] == picture["start_anchor"]

    # An illegal depth/position pairing (behind, only ever legal over aroll) is rejected --
    # `Cut`'s own matrix validator, surfaced as a 400 by the generic ops dispatcher.
    rev2 = client.get(f"/api/projects/{pid}/cuts/{cut_id}").json()["revision"]
    r = client.post(f"/api/projects/{pid}/cuts/{cut_id}/ops", json={
        "name": "add_beat_spans",
        "args": {
            "sync_group_id": sync_group_id, "start_word_id": word_ids[3], "end_word_id": word_ids[3],
            "picture_kind": "motion_graphic", "brief_text": "A chart.",
            "overlay_depth": "behind", "overlay_position": "full-frame",
        },
        "expected_rev": rev2,
    })
    assert r.status_code == 400, r.text
