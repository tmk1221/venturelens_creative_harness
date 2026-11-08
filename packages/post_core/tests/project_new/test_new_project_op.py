"""T34: `new_project` end to end on lavfi media in temp dirs -- what it writes, where, that the
footage is never touched, that a re-run skips every finished step, and plain-word failures."""
from __future__ import annotations

import json

import pytest

from post_core.project_new import NewProjectError, ensure_first_cut, new_project
from post_core.store import store as store_module
from post_core.store.paths import store_root

from .conftest import make_recording, requires_ffmpeg

pytestmark = requires_ffmpeg


def _snapshot(folder):
    return {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(folder.iterdir())}


def test_new_project_builds_everything_inside_the_project(tmp_path, footage, clip, words_file, kits):
    before = _snapshot(footage)
    events: list[dict] = []
    root = tmp_path / "projects" / "keith"
    out = new_project(root, "Sample sample", [clip], transcripts=[words_file], kit="show", emit=events.append)

    assert [s["status"] for s in out["steps"]] == ["done"] * 8
    assert [s["step"] for s in out["steps"]] == [
        "check", "init", "kit", "source:0", "audio:0", "peaks:0", "transcript:0", "cut"]
    project, _ = store_module.read(root, "project")
    assert (project.name, project.brand_kit) == ("Sample sample", "show")

    shoot, _ = store_module.read(root, "shoot", out["sources"][0]["shoot_id"])
    (source,) = shoot.sources
    (group,) = shoot.sync_groups
    assert source.path == str(clip.resolve()) and source.role == "a_roll" and group.source_ids == [source.id]
    assert source.content_fingerprint and source.audio_proxy_path.startswith(str(store_root(root)))
    assert source.peaks_path.startswith(str(store_root(root)))
    assert shoot.transcript_ids == out["transcript_ids"]

    cut, _ = store_module.read(root, "cut", out["cut_id"])
    transcript, _ = store_module.read(root, "transcript", out["transcript_ids"][0])
    assert {w.speaker for w in transcript.words} == {"SPEAKER_00", "SPEAKER_01"}
    assert [(p.start_word_id, p.end_word_id, p.angle_source_id) for p in cut.passages] == [
        (transcript.words[0].id, transcript.words[-1].id, source.id)]

    assert _snapshot(footage) == before  # read-only: nothing new or changed next to the footage
    statuses = [(e["step"], e["status"]) for e in events if e["kind"] == "step"]
    assert statuses[:8] == [(s, "pending") for s in ("check", "init", "kit", "source:0", "audio:0", "peaks:0",
                                                      "transcript:0", "cut")]
    assert ("audio:0", "running") in statuses and ("audio:0", "done") in statuses
    progress = [e for e in events if e["kind"] == "progress"]
    assert progress and {e["step"] for e in progress} == {"audio:0"} and all(e["n"] == 100 for e in progress)


def test_rerun_is_idempotent(tmp_path, footage, clip, words_file, kits):
    root = tmp_path / "proj"
    first = new_project(root, "P", [clip], transcripts=[words_file], kit="show")
    proxy = store_root(root) / "proxies"
    proxy_mtimes = _snapshot(proxy)

    again = new_project(root, "P", [clip], transcripts=[words_file], kit="show")
    assert [s["status"] for s in again["steps"]] == ["done"] + ["skipped"] * 7
    assert again["sources"][0]["source_id"] == first["sources"][0]["source_id"]
    assert again["cut_id"] == first["cut_id"] and again["transcript_ids"] == first["transcript_ids"]
    assert _snapshot(proxy) == proxy_mtimes
    shoot, _ = store_module.read(root, "shoot", first["sources"][0]["shoot_id"])
    assert len(shoot.sources) == 1 and len(shoot.sync_groups) == 1 and len(shoot.transcript_ids) == 1
    assert len(list((store_root(root) / "cuts").glob("*.json"))) == 1


def test_resumes_after_a_partial_run(tmp_path, footage, clip):
    root = tmp_path / "proj"
    new_project(root, "P", [clip])
    # Lose the peaks (as if the run died before that step): only that step runs again.
    for p in (store_root(root) / "peaks").iterdir():
        p.unlink()
    out = new_project(root, "P", [clip])
    assert {s["step"]: s["status"] for s in out["steps"]}["peaks:0"] == "done"
    assert {s["step"]: s["status"] for s in out["steps"]}["audio:0"] == "skipped"


def test_one_sync_group_per_file_and_audio_only_role(tmp_path, footage, clip):
    wav = make_recording(footage / "recorder.wav", video=False)
    out = new_project(tmp_path / "proj", None, [clip, wav])
    shoot, _ = store_module.read(tmp_path / "proj", "shoot", out["sources"][0]["shoot_id"])
    assert [s.role for s in shoot.sources] == ["a_roll", "audio"]
    assert sorted(len(g.source_ids) for g in shoot.sync_groups) == [1, 1]
    assert out["name"] == "proj" and out["cut_id"] is None


def test_open_editor_cut_needs_a_transcript_then_is_made_once(tmp_path, footage, clip, words_file):
    root = tmp_path / "proj"
    out = new_project(root, "P", [clip])
    with pytest.raises(ValueError, match="no transcript yet"):
        ensure_first_cut(root)
    from post_core.project_new.steps import import_transcript

    src = out["sources"][0]
    import_transcript(root, src["shoot_id"], src["sync_group_id"], words_file)
    cut_id, created = ensure_first_cut(root)
    assert created and ensure_first_cut(root) == (cut_id, False)


def test_failures_are_plain_words(tmp_path, footage, clip):
    events: list[dict] = []
    notmedia = footage / "notes.mp4"
    notmedia.write_text("not a video")
    with pytest.raises(NewProjectError) as err:
        new_project(tmp_path / "proj", "P", [notmedia], emit=events.append)
    assert err.value.step == "source:0" and "ffmpeg could not read the file" in str(err.value)
    failed = [e for e in events if e.get("status") == "failed"]
    assert failed == [{"kind": "step", "step": "source:0", "label": "Add notes.mp4", "status": "failed",
                       "error": str(err.value)}]

    silent = make_recording(footage / "silent.mp4", audio=False)
    with pytest.raises(NewProjectError, match="has no audio track"):
        new_project(tmp_path / "proj2", "P", [silent])

    with pytest.raises(NewProjectError, match="Can't find the recording"):
        new_project(tmp_path / "proj3", "P", [footage / "missing.mp4"])
    assert not (tmp_path / "proj3").exists()

    bad = footage / "bad.json"
    bad.write_text(json.dumps([{"start": 0, "end": 1}]))
    with pytest.raises(NewProjectError, match="Couldn't read the transcript bad.json"):
        new_project(tmp_path / "proj4", "P", [clip], transcripts=[bad])


def test_unknown_kit_is_refused_before_anything_is_written(tmp_path, clip, kits):
    with pytest.raises(NewProjectError, match="unknown brand kit 'nope'; available: _demo, show"):
        new_project(tmp_path / "proj", "P", [clip], kit="nope")
    assert not (tmp_path / "proj").exists()
