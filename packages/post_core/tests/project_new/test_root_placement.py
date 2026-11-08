"""T34/T39: a project root is never the footage's own folder, never inside it, never inside a
library `Video/source` folder -- and a refusal happens before anything is written. An external
drive is fine now (the media library lives there). Plus the CLI end to end."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from post_core.project_new import RootPlacementError, check_root_placement, new_project

from .conftest import make_recording, requires_ffmpeg, two_speaker_words


def test_refuses_the_sources_own_folder_and_anything_under_it(tmp_path):
    src = tmp_path / "footage" / "ep.mp4"
    with pytest.raises(RootPlacementError, match="is the folder ep.mp4 is in"):
        check_root_placement(tmp_path / "footage", [src])
    with pytest.raises(RootPlacementError, match="inside the footage folder"):
        check_root_placement(tmp_path / "footage" / "post" / "proj", [src])
    # A sibling, or a folder that merely contains the footage folder, is fine.
    assert check_root_placement(tmp_path / "proj", [src]) == (tmp_path / "proj").resolve()
    assert check_root_placement(tmp_path, [src]) == tmp_path.resolve()


def test_refuses_a_video_source_folder_but_not_the_drive(tmp_path):
    source_dir = tmp_path / "Drive" / "Co" / "Proj" / "Video" / "source"
    clip = source_dir / "ep.mp4"
    for bad in (source_dir, source_dir / "proj", source_dir / "a" / "b"):
        with pytest.raises(RootPlacementError, match="inside the footage folder .*Video/source"):
            check_root_placement(bad)
    # The library project folder that holds `Video/source` is where Post writes.
    project = tmp_path / "Drive" / "Co" / "Proj"
    assert check_root_placement(project, [clip]) == project.resolve()


def test_a_symlink_into_a_source_folder_is_caught(tmp_path):
    source_dir = tmp_path / "Co" / "Proj" / "Video" / "source"
    source_dir.mkdir(parents=True)
    (tmp_path / "shortcut").symlink_to(source_dir)
    with pytest.raises(RootPlacementError, match="inside the footage folder"):
        check_root_placement(tmp_path / "shortcut" / "proj")


@requires_ffmpeg
def test_new_project_refuses_before_writing(tmp_path):
    clip = make_recording(tmp_path / "footage" / "ep.mp4")
    for bad_root in (tmp_path / "footage", tmp_path / "footage" / "proj"):
        with pytest.raises(Exception, match="footage"):
            new_project(bad_root, "P", [clip])
    assert sorted(p.name for p in (tmp_path / "footage").iterdir()) == ["ep.mp4"]


def _cli(*args: str, env: dict) -> tuple[int, list[dict]]:
    proc = subprocess.run([sys.executable, "-m", "post_core.cli.main", *args],
                          capture_output=True, text=True, timeout=120, env=env)
    return proc.returncode, [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


@requires_ffmpeg
def test_cli_smoke_60s_two_voice_file_to_an_editable_cut(tmp_path):
    """The acceptance smoke run: one command on a generated 60 s two-voice recording, one
    JSON line per step, then the cut takes an edit (`cut op delete_words`)."""
    clip = make_recording(tmp_path / "footage" / "two_voice.mp4", seconds=60)
    words = tmp_path / "footage" / "two_voice.words.json"
    words.write_text(json.dumps({"words": two_speaker_words(60)}))
    env = {**os.environ, "POST_CORE_ENV_FILE": str(tmp_path / "none.env")}
    root = tmp_path / "Post" / "smoke"

    code, lines = _cli("project", "new", "Smoke", "--root", str(root), "--source", str(clip),
                       "--transcript", str(words), env=env)
    assert code == 0, lines
    *step_lines, result = lines
    assert [line["step"] for line in step_lines] == [
        "check", "init", "source:0", "audio:0", "peaks:0", "transcript:0", "cut"]
    assert all(line["status"] == "done" for line in step_lines) and result["cut_id"]

    transcript = json.loads((root / ".post3" / "transcripts" / f"{result['transcript_ids'][0]}.json").read_text())
    first, second = transcript["data"]["words"][:2]
    code, lines = _cli("cut", "op", "delete_words", "--root", str(root), "--cut", result["cut_id"], "--args",
                       json.dumps({"sync_group_id": result["sources"][0]["sync_group_id"],
                                   "start_word_id": first["id"], "end_word_id": second["id"]}), env=env)
    assert code == 0, lines

    code, lines = _cli("project", "new", "Smoke", "--root", str(root), "--source", str(clip),
                       "--transcript", str(words), env=env)
    assert code == 0 and [line["status"] for line in lines[:-1]] == ["done"] + ["skipped"] * 6

    bad = tmp_path / "Co" / "P" / "Video" / "source" / "x"
    code, lines = _cli("project", "new", "Bad", "--root", str(bad), "--source", str(clip), env=env)
    assert code == 1 and "inside the footage folder" in lines[-1]["error"]
    code, lines = _cli("init", str(bad), env=env)
    assert code == 1 and "inside the footage folder" in lines[-1]["error"]
    assert not bad.exists()
