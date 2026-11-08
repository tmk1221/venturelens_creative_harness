"""T36: `brief.write` and `motion.from_frame` in real mode ask the project's terminal agent
(the `fake_agent` script on PATH -- never a real `claude`/`codex`), write only a validated
reply, and fail with the agent's reason otherwise. Fake mode (the recipes conftest default)
never calls an agent."""
from __future__ import annotations

import json

import pytest

from post_core.recipes.workers import brief_write, motion_from_frame
from post_core.workers.contract import parse_line


def _events(capsys) -> list[dict]:
    return [e for e in (parse_line(line) for line in capsys.readouterr().out.splitlines()) if e]


@pytest.fixture
def real_mode(monkeypatch):
    monkeypatch.delenv("POST3_FAKE_PROVIDERS", raising=False)


def _brief_argv(project_root, out, writer_context=None):
    return [
        "--node-id", "b1", "--project-root", str(project_root), "--instruction", "a title card",
        "--words-text", "we grew revenue forty percent", "--direction-note", "open with the number",
        "--writer-context", json.dumps(writer_context if writer_context is not None else {"identity": "Bicycle repair"}),
        "--out", str(out),
    ]


def test_brief_write_real_mode_asks_the_agent_with_brand_words_and_direction(
    tmp_path, project_root, fake_agent, real_mode, capsys,
):
    fake_agent.reply({"brief": "A bar climbs to forty percent, then the number lands."})
    out = tmp_path / "brief.txt"
    assert brief_write.main(_brief_argv(project_root, out)) == 0
    assert out.read_text(encoding="utf-8") == "A bar climbs to forty percent, then the number lands."
    [call] = fake_agent.calls()
    for expected in ("Identity: Bicycle repair", "we grew revenue forty percent", "open with the number", '{"brief"'):
        assert expected in call["prompt"]
    events = _events(capsys)
    prompt_event = next(e for e in events if e["kind"] == "prompt")
    assert prompt_event["text"] == call["prompt"]
    assert prompt_event["model"] == "claude / CLI default"
    assert events[-1]["kind"] == "result" and events[-1]["ok"] is True


def test_brief_write_falls_back_to_the_project_kit_when_the_node_has_no_context(
    tmp_path, project_root, fake_agent, real_mode, monkeypatch,
):
    from post_core import brand

    monkeypatch.setattr(brand, "project_writer_context", lambda root: {"identity": "Project kit identity"})
    fake_agent.reply({"brief": "x"})
    assert brief_write.main(_brief_argv(project_root, tmp_path / "brief.txt", writer_context={})) == 0
    assert "Identity: Project kit identity" in fake_agent.calls()[0]["prompt"]


@pytest.mark.parametrize("reply", ["not json at all", '{"brief": "  "}', '{"text": "wrong key"}'])
def test_brief_write_bad_reply_writes_nothing(tmp_path, project_root, fake_agent, real_mode, capsys, reply):
    fake_agent.reply(reply)
    out = tmp_path / "brief.txt"
    assert brief_write.main(_brief_argv(project_root, out)) == 1
    assert not out.exists()
    result = _events(capsys)[-1]
    assert result["kind"] == "result" and result["ok"] is False and result["reason"] == "bad_json"


def test_brief_write_fake_mode_never_calls_the_agent(tmp_path, project_root, fake_agent):
    assert brief_write.main(_brief_argv(project_root, tmp_path / "brief.txt")) == 0
    assert fake_agent.calls() == []


def _motion_argv(project_root, kit, frame, out):
    return [
        "--node-id", "m1", "--project-root", str(project_root), "--kit-dir", str(kit.path),
        "--frame", str(frame), "--subject-motion-hint", "the rider moves", "--static-hint", "the background",
        "--out", str(out),
    ]


@pytest.fixture
def frame(tmp_path):
    path = tmp_path / "picked" / "frame.png"
    path.parent.mkdir()
    path.write_bytes(b"png")
    return path


def test_motion_from_frame_real_mode_looks_at_the_frame_and_keeps_the_kit_camera(
    tmp_path, project_root, kit, frame, fake_agent, real_mode, capsys,
):
    fake_agent.reply({"subject_motion": "the rider pedals slowly toward the window.", "static": "the workbench"})
    out = tmp_path / "motion_prompt.txt"
    assert motion_from_frame.main(_motion_argv(project_root, kit, frame, out)) == 0
    text = out.read_text(encoding="utf-8")
    assert "Subject motion: the rider pedals slowly toward the window." in text
    assert "Static: the workbench." in text
    assert "Camera: slow, deliberate moves." in text  # the kit's camera; the agent never sets it
    [call] = fake_agent.calls()
    args = call["args"]
    assert args[args.index("--tools") + 1] == "Read"
    assert args[args.index("--add-dir") + 1] == str(frame.parent)
    assert str(frame) in call["prompt"] and "the rider moves" in call["prompt"]
    assert "Identity: widgets" in call["prompt"]
    kinds = [e["kind"] for e in _events(capsys)]
    assert kinds.count("prompt") == 2 and kinds[-1] == "result"


@pytest.mark.parametrize("subject", ["a #FF6600 glow pulses", "the Acme sign flickers"])
def test_motion_from_frame_refuses_brand_impure_agent_text(tmp_path, project_root, kit, frame, fake_agent, real_mode, subject):
    fake_agent.reply({"subject_motion": subject, "static": "the wall"})
    out = tmp_path / "motion_prompt.txt"
    assert motion_from_frame.main(_motion_argv(project_root, kit, frame, out)) == 1
    assert not out.exists()


def test_motion_from_frame_without_an_agent_fails_with_the_reason(tmp_path, project_root, kit, frame, real_mode, capsys):
    # No `fake_agent`: the suite guard points both CLIs at a path that does not exist.
    out = tmp_path / "motion_prompt.txt"
    assert motion_from_frame.main(_motion_argv(project_root, kit, frame, out)) == 1
    assert not out.exists()
    result = _events(capsys)[-1]
    assert result["ok"] is False and result["reason"] == "not_found" and "claude CLI not found" in result["detail"]


def test_motion_from_frame_fake_mode_uses_the_hints_without_an_agent(tmp_path, project_root, kit, frame, fake_agent):
    out = tmp_path / "motion_prompt.txt"
    assert motion_from_frame.main(_motion_argv(project_root, kit, frame, out)) == 0
    assert "Subject motion: the rider moves." in out.read_text(encoding="utf-8")
    assert fake_agent.calls() == []
