"""T42: `post project set --picture-mode presenter|audio_only` writes only the project record."""
from __future__ import annotations


def test_set_picture_mode(run_cli, tmp_path):
    root = tmp_path / "proj"
    assert run_cli("init", str(root))["exit_code"] == 0
    assert run_cli("project", "show", "--root", str(root))["project"]["picture_mode"] == "presenter"

    nothing = run_cli("project", "set", "--root", str(root))
    assert nothing["exit_code"] == 1 and "--picture-mode" in nothing["error"]

    done = run_cli("project", "set", "--picture-mode", "audio_only", "--root", str(root))
    assert done["exit_code"] == 0, done
    assert done["picture_mode"] == "audio_only" and done["previous"] == "presenter"
    assert run_cli("project", "show", "--root", str(root))["project"]["picture_mode"] == "audio_only"
