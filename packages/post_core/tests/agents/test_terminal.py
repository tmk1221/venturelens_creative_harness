"""T36: `post_core.agents.ask_json` against a fake agent script on PATH (`fake_agent`, root
conftest) -- never a real `claude`/`codex`. Success for both providers, per-operation
provider/model from `.post3/agents.json`, images, timeout, bad JSON, a failing CLI and a
missing binary."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

import pytest

from post_core import store
from post_core.agents import (
    AgentBadJSON,
    AgentConfigError,
    AgentError,
    AgentFailed,
    AgentNotFound,
    AgentTimeout,
    ask_json,
    choice_for,
)
from post_core.agents.terminal import PREAMBLE


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    store.init_project(root)
    return root


def _configure(project, config: dict) -> None:
    (project / ".post3" / "agents.json").write_text(json.dumps(config), encoding="utf-8")


def test_claude_by_default_read_only_no_mcp_no_session_prompt_on_stdin(fake_agent, project, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
    fake_agent.reply('{"ok": true, "n": 3}')
    assert ask_json('A "quoted" prompt\nwith $shell text', "brief_write", project_root=project) == {"ok": True, "n": 3}
    [call] = fake_agent.calls()
    args = call["args"]
    assert call["name"] == "claude"
    assert args[0] == "-p"
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert "--no-session-persistence" in args
    assert "--strict-mcp-config" in args
    assert json.loads(args[args.index("--mcp-config") + 1]) == {"mcpServers": {}}
    assert "--model" not in args  # the CLI's own default unless agents.json names one
    assert call["prompt"] == PREAMBLE + 'A "quoted" prompt\nwith $shell text'
    assert call["spend_keys"] == []  # subscription only: API keys never reach the agent
    assert not call["cwd"].startswith(str(project))


def test_codex_per_operation_from_agents_json_reads_only_the_final_message(fake_agent, project):
    _configure(project, {"default": {"provider": "claude"},
                         "suggest_visuals": {"provider": "codex", "model": "gpt-test"}})
    fake_agent.reply({"proposals": []})
    assert ask_json("suggest", "suggest_visuals", project_root=project) == {"proposals": []}
    assert ask_json("brief", "brief_write", project_root=project) == {"proposals": []}
    codex, claude = fake_agent.calls()
    assert (codex["name"], claude["name"]) == ("codex", "claude")
    args = codex["args"]
    assert args[:3] == ["exec", "--sandbox", "read-only"]
    assert "--ephemeral" in args and "--skip-git-repo-check" in args
    assert args[args.index("-c") + 1] == "mcp_servers={}"
    assert args[args.index("--model") + 1] == "gpt-test"
    assert args[-2:] == ["--", "-"]
    assert codex["prompt"].endswith("suggest")


def test_images_are_attached_read_only_for_both_providers(fake_agent, project, tmp_path):
    frame = tmp_path / "frames" / "start frame.png"
    frame.parent.mkdir()
    frame.write_bytes(b"png")
    for provider in ("claude", "codex"):
        _configure(project, {"motion_from_frame": {"provider": provider}})
        ask_json("look", "motion_from_frame", images=[frame], project_root=project)
    claude, codex = fake_agent.calls()
    assert str(frame) in claude["prompt"] and str(frame) in codex["prompt"]
    assert claude["args"][claude["args"].index("--tools") + 1] == "Read"
    assert claude["args"][claude["args"].index("--allowedTools") + 1] == "Read"
    assert claude["args"][claude["args"].index("--add-dir") + 1] == str(frame.parent)
    assert codex["args"][codex["args"].index("--image") + 1] == str(frame)


def test_on_prompt_sees_the_exact_text_and_the_choice(fake_agent, project):
    _configure(project, {"brief_write": {"model": "sonnet"}})
    seen = []
    ask_json("hello", "brief_write", project_root=project, on_prompt=lambda text, choice: seen.append((text, choice)))
    [(text, choice)] = seen
    assert text == fake_agent.calls()[0]["prompt"]
    assert (choice.provider, choice.model, choice.label) == ("claude", "sonnet", "claude / sonnet")


def test_timeout_kills_the_agent_and_says_so(fake_agent, project):
    fake_agent.mode("sleep")
    with pytest.raises(AgentTimeout, match="timed out after 0.5 s"):
        ask_json("slow", "brief_write", timeout=0.5, project_root=project)
    pid = fake_agent.calls()[0]["pid"]
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_cancelling_the_worker_stops_its_agent(fake_agent):
    """A cancelled queue job gets SIGTERM; the agent runs in its own session, so the worker
    must take it down too."""
    fake_agent.mode("sleep")
    worker = subprocess.Popen(
        [sys.executable, "-c", "from post_core.agents import ask_json; ask_json('fixture', 'brief_write')"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while not fake_agent.calls() and time.monotonic() < deadline:
            time.sleep(0.02)
        [call] = fake_agent.calls()
        worker.send_signal(signal.SIGTERM)
        assert worker.wait(timeout=10) == 128 + signal.SIGTERM
        with pytest.raises(ProcessLookupError):
            os.kill(call["pid"], 0)
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()


def test_timeout_comes_from_agents_json(fake_agent, project):
    _configure(project, {"default": {"timeout_seconds": 0.5}})
    fake_agent.mode("sleep")
    with pytest.raises(AgentTimeout):
        ask_json("slow", "suggest_visuals", project_root=project)


@pytest.mark.parametrize("reply", ["[]", 'Sure! {"ok": true}', "{broken", ""])
def test_bad_json_is_refused(fake_agent, project, reply):
    fake_agent.reply(reply)
    with pytest.raises(AgentBadJSON, match="brief_write"):
        ask_json("x", "brief_write", project_root=project)


def test_fenced_json_is_accepted(fake_agent, project):
    fake_agent.reply('```json\n{"ok": true}\n```')
    assert ask_json("x", "brief_write", project_root=project) == {"ok": True}


def test_codex_without_a_final_message_is_not_a_result(fake_agent, project):
    _configure(project, {"default": {"provider": "codex"}})
    fake_agent.mode("no-final")
    with pytest.raises(AgentBadJSON, match="no final message"):
        ask_json("x", "brief_write", project_root=project)


def test_failing_cli_surfaces_its_stderr_without_falling_back(fake_agent, project):
    fake_agent.mode("fail")
    with pytest.raises(AgentFailed, match="Usage limit reached") as info:
        ask_json("x", "brief_write", project_root=project)
    assert info.value.reason == "failed"
    assert [c["name"] for c in fake_agent.calls()] == ["claude"]


def test_missing_binary_fails_before_any_call(fake_agent, project, tmp_path, monkeypatch):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))  # nothing named claude anywhere -- never the real one
    with pytest.raises(AgentNotFound, match="claude CLI not found"):
        ask_json("x", "brief_write", project_root=project)
    _configure(project, {"default": {"provider": "codex"}})
    with pytest.raises(AgentNotFound, match="POST3_CODEX_BIN"):
        ask_json("x", "brief_write", project_root=project)
    assert fake_agent.calls() == []


def test_binary_is_injectable(fake_agent, project, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ask_json("x", "brief_write", project_root=project, binary=str(fake_agent.bin_dir / "claude")) == {"ok": True}
    monkeypatch.setenv("POST3_CLAUDE_BIN", str(fake_agent.bin_dir / "claude"))
    assert ask_json("x", "brief_write", project_root=project) == {"ok": True}
    assert len(fake_agent.calls()) == 2


def test_binary_that_cannot_start_is_a_clear_failure(fake_agent, project, tmp_path):
    broken = tmp_path / "claude-not-executable"
    broken.write_text("#!/bin/sh\n", encoding="utf-8")
    broken.chmod(0o644)
    with pytest.raises(AgentNotFound):  # `which` refuses a non-executable file
        ask_json("x", "brief_write", project_root=project, binary=str(broken))
    bad_interpreter = tmp_path / "claude-bad-interpreter"
    bad_interpreter.write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
    bad_interpreter.chmod(0o755)
    with pytest.raises(AgentFailed, match="could not start"):
        ask_json("x", "brief_write", project_root=project, binary=str(bad_interpreter))


def test_missing_image_fails_before_any_call(fake_agent, project, tmp_path):
    with pytest.raises(AgentError, match="image is missing"):
        ask_json("x", "motion_from_frame", images=[tmp_path / "nope.png"], project_root=project)
    assert fake_agent.calls() == []


def test_config_errors_are_clear(project):
    assert choice_for("brief_write", project).provider == "claude"
    for bad, match in (
        ({"default": {"provider": "gemini"}}, "unknown provider"),
        ({"brief_wrte": {}}, "unknown key"),
        ({"default": {"modle": "x"}}, "unknown field"),
        ({"default": {"timeout_seconds": 0}}, "positive"),
    ):
        _configure(project, bad)
        with pytest.raises(AgentConfigError, match=match):
            choice_for("brief_write", project)
    (project / ".post3" / "agents.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(AgentConfigError, match="not valid JSON"):
        choice_for("brief_write", project)
    with pytest.raises(AgentConfigError, match="unknown agent operation"):
        choice_for("animation_design", None)
