"""T36: `ask_json` -- one read-only JSON call through a terminal agent (Claude Code's `claude
-p` or `codex exec`) on the user's own subscription. No SDK, no API key, no implicit fallback
from one provider to the other, no model-name translation.

Ported from the old flow's `~/.claude/skills/post/scripts/terminal_agent.py` (same flags, same
stdin prompt, same final-message rule), with three changes: provider/model/timeout come from
`<project>/.post3/agents.json` per operation (`agents.config`), failures are typed
(`agents.errors`), and API-key variables are removed from the agent's environment so a call
can only ever run on the signed-in subscription, never bill API dollars.

What the agent can do: nothing but read. Claude runs with no tools at all (`--tools ""`), or
only `Read` limited to the attached images' folders; no MCP servers; no saved session.
Codex runs in its read-only sandbox, ephemeral, with MCP servers cleared. Both run in an
empty temp directory, the prompt arrives on stdin, and only the final message counts: tool
events and narration are never a result. Nothing here writes project files -- callers write
only after validating the parsed reply.

`binary=` (or `$POST3_CLAUDE_BIN` / `$POST3_CODEX_BIN`) points at a specific executable;
tests use a fake script, never a real agent.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Iterable, Optional

from .config import AgentChoice, choice_for
from .errors import AgentBadJSON, AgentError, AgentFailed, AgentNotFound, AgentTimeout

BIN_ENV = {"claude": "POST3_CLAUDE_BIN", "codex": "POST3_CODEX_BIN"}
# Present in the parent's environment, these would switch a CLI from the subscription login to
# per-token API billing. The agent never sees them.
SPEND_ENV_KEYS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY")
PREAMBLE = "Inspect the supplied material without changing any file. Return only the requested JSON object.\n\n"
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")
_TAIL_CHARS = 1200

OnPrompt = Callable[[str, AgentChoice], None]


def find_binary(provider: str, binary: Optional[str] = None) -> str:
    requested = binary or os.environ.get(BIN_ENV[provider]) or provider
    found = shutil.which(requested)
    if not found:
        raise AgentNotFound(
            f"{provider} CLI not found ({requested}); install it and sign in, put it on PATH, "
            f"or set {BIN_ENV[provider]}"
        )
    return found


def parse_object(text: str) -> dict:
    """The final message as one JSON object (a ```json fence is tolerated, prose is not)."""
    value = _FENCE_RE.sub("", text.strip()).strip()
    if not value:
        raise AgentBadJSON("the agent's final message was empty; nothing was applied")
    try:
        data = json.loads(value)
    except ValueError as exc:
        raise AgentBadJSON(f"the agent's final message is not valid JSON; nothing was applied: {value[:200]!r}") from exc
    if not isinstance(data, dict):
        raise AgentBadJSON("the agent must return one JSON object; nothing was applied")
    return data


def build_command(provider: str, binary: str, model: Optional[str], images: list[Path], final: Path) -> list[str]:
    if provider == "codex":
        # UNVERIFIED: `-c mcp_servers={}` (clear every configured MCP server) has not been run
        # against a real codex; the rest of this argv is the old flow's, used in production.
        cmd = [binary, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--ephemeral",
               "--json", "--output-last-message", str(final), "-c", "mcp_servers={}"]
        for path in images:
            cmd += ["--image", str(path)]
        if model:
            cmd += ["--model", model]
        return cmd + ["--", "-"]
    cmd = [binary, "-p", "--tools", "Read" if images else "", "--permission-mode", "dontAsk",
           "--no-session-persistence", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    if images:
        cmd += ["--allowedTools", "Read"]
        for folder in sorted({str(p.parent) for p in images}):
            cmd += ["--add-dir", folder]
    if model:
        cmd += ["--model", model]
    return cmd


def _child_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in SPEND_ENV_KEYS}


def _stop(proc: subprocess.Popen) -> None:
    """Stop the agent's whole process group: the leader may be gone while a tool child lives."""
    for sig, wait in ((signal.SIGTERM, 2), (signal.SIGKILL, None)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            pass


def _tail(stream) -> str:
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(max(0, size - 4 * _TAIL_CHARS))
    return stream.read()[-_TAIL_CHARS:]


def _run(cmd: list[str], stdin_text: str, cwd: Path, timeout: float, what: str, keep_stdout: bool) -> tuple[int, str, str]:
    """(exit code, stdout -- whole if `keep_stdout`, else its tail -- , stderr tail)."""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as out, \
            tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as err:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=out, stderr=err, text=True,
                                    encoding="utf-8", start_new_session=True, env=_child_env())
        except OSError as exc:  # e.g. not executable, bad interpreter line
            raise AgentFailed(f"{what} could not start {cmd[0]}: {exc}") from exc
        interrupted = False
        previous = None

        def _terminate(signum, _frame):
            # A cancelled worker gets SIGTERM; its agent is in its own session, so stop it too.
            nonlocal interrupted
            interrupted = True
            raise SystemExit(128 + signum)

        if threading.current_thread() is threading.main_thread():
            previous = signal.signal(signal.SIGTERM, _terminate)
        try:
            try:
                proc.communicate(input=stdin_text, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                interrupted = True
                raise AgentTimeout(f"{what} timed out after {timeout:g} s; the agent was stopped") from exc
            out.seek(0)
            stdout = out.read() if keep_stdout else _tail(out)
            return proc.returncode, stdout, _tail(err)
        finally:
            if previous is not None:
                signal.signal(signal.SIGTERM, previous)
            if interrupted or proc.poll() is None:
                _stop(proc)


def ask_json(
    prompt: str,
    operation: str,
    images: Iterable[str | Path] = (),
    timeout: Optional[float] = None,
    *,
    project_root: Optional[str | Path] = None,
    binary: Optional[str] = None,
    on_prompt: Optional[OnPrompt] = None,
) -> dict:
    """Run `operation`'s agent on `prompt` (stdin) and return its final message as a dict.
    `images` are attached read-only; `timeout` overrides the configured one; `on_prompt` sees
    the exact text sent (workers record it as a `prompt` event). Raises an `AgentError`."""
    choice = choice_for(operation, project_root)
    executable = find_binary(choice.provider, binary)
    paths = [Path(p).resolve() for p in images]
    for path in paths:
        if not path.is_file():
            raise AgentError(f"{operation}: image is missing: {path}")
    effective = PREAMBLE + prompt
    if paths:
        effective += "\n\nImages, in attachment order:\n" + "\n".join(map(str, paths))
    limit = choice.timeout_seconds if timeout is None else timeout
    what = f"{operation} ({choice.label})"
    if on_prompt is not None:
        on_prompt(effective, choice)
    with tempfile.TemporaryDirectory(prefix="post3-agent-") as temp:
        directory = Path(temp)
        final = directory / "final.json"
        cmd = build_command(choice.provider, executable, choice.model, paths, final)
        code, stdout, stderr = _run(cmd, effective, directory, limit, what, keep_stdout=choice.provider == "claude")
        if code:
            detail = (stderr.strip() or stdout.strip())[-_TAIL_CHARS:]
            raise AgentFailed(f"{what} failed (exit {code}): {detail or 'no output'}")
        if choice.provider == "codex":
            if not final.is_file():
                raise AgentBadJSON(f"{what} returned no final message; tool events are not a result")
            reply = final.read_text(encoding="utf-8")
        else:
            reply = stdout
    try:
        return parse_object(reply)
    except AgentBadJSON as exc:
        raise AgentBadJSON(f"{what}: {exc}") from None


__all__ = ["BIN_ENV", "SPEND_ENV_KEYS", "find_binary", "parse_object", "build_command", "ask_json"]
