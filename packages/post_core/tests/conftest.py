"""Suite-wide guard (T36): no test may ever run the real `claude` or `codex` CLI. Both binary
overrides point at a path that does not exist, so a real-mode agent call that a test forgot
to fake fails with `AgentNotFound` instead of reaching a signed-in agent.

`fake_agent` is the one sanctioned stand-in: a script installed as both `claude` and `codex`
on a temp dir prepended to PATH (overrides removed), which records each call (argv, stdin
prompt, cwd, pid, which API-key variables it could see) to a JSON-lines log and answers per
`FAKE_AGENT_MODE`: a canned reply (default), `sleep`, `fail` (stderr + exit 2), or
`no-final` (codex writes no last message)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

BLOCKED_AGENT_BIN = "/nonexistent/post3-tests-never-run-a-real-agent"

_FAKE_AGENT = r'''
import json, os, pathlib, sys, time
args = sys.argv[1:]
prompt = sys.stdin.read()
keys = [k for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY") if k in os.environ]
record = {"name": pathlib.Path(sys.argv[0]).name, "args": args, "prompt": prompt, "pid": os.getpid(),
          "cwd": os.getcwd(), "spend_keys": keys}
with open(os.environ["FAKE_AGENT_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(record) + "\n")
mode = os.environ.get("FAKE_AGENT_MODE", "")
if mode == "sleep":
    time.sleep(30)
if mode == "fail":
    print("Usage limit reached; try again at 5pm", file=sys.stderr)
    sys.exit(2)
reply = os.environ.get("FAKE_AGENT_REPLY", '{"ok": true}')
if "exec" in args:
    print('{"type": "item.completed", "not": "the final message"}')
    if mode != "no-final":
        pathlib.Path(args[args.index("--output-last-message") + 1]).write_text(reply)
else:
    print(reply)
'''


@pytest.fixture(autouse=True)
def _no_real_terminal_agents(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("POST3_CLAUDE_BIN", BLOCKED_AGENT_BIN)
    monkeypatch.setenv("POST3_CODEX_BIN", BLOCKED_AGENT_BIN)
    # T39: no test ever reads the real media library (or `~/.post3rc`).
    monkeypatch.setenv("POST3_LIBRARY", str(tmp_path_factory.getbasetemp() / "no-library"))
    monkeypatch.setenv("POST3_RC", str(tmp_path_factory.getbasetemp() / "no-post3rc"))
    monkeypatch.setenv("POST3_HIGGSFIELD_BIN", "/nonexistent/post3-tests-never-run-higgsfield")
    yield


@dataclass
class FakeAgent:
    bin_dir: Path
    log: Path
    monkeypatch: pytest.MonkeyPatch

    def reply(self, value) -> None:
        self.monkeypatch.setenv("FAKE_AGENT_REPLY", value if isinstance(value, str) else json.dumps(value))

    def mode(self, mode: str) -> None:
        self.monkeypatch.setenv("FAKE_AGENT_MODE", mode)

    def calls(self) -> list[dict]:
        if not self.log.is_file():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture
def fake_agent(tmp_path, monkeypatch, _no_real_terminal_agents) -> FakeAgent:
    bin_dir = tmp_path / "fake-agent-bin"
    bin_dir.mkdir()
    for name in ("claude", "codex"):
        script = bin_dir / name
        script.write_text(f"#!{sys.executable}\n{_FAKE_AGENT}", encoding="utf-8")
        script.chmod(0o755)
    log = tmp_path / "fake-agent-calls.jsonl"
    monkeypatch.delenv("POST3_CLAUDE_BIN")
    monkeypatch.delenv("POST3_CODEX_BIN")
    monkeypatch.delenv("FAKE_AGENT_MODE", raising=False)
    monkeypatch.delenv("FAKE_AGENT_REPLY", raising=False)
    monkeypatch.setenv("FAKE_AGENT_LOG", str(log))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return FakeAgent(bin_dir=bin_dir, log=log, monkeypatch=monkeypatch)
