"""Shared fixtures for driving `post` (packages/post_core/post_core/cli) via subprocess,
exactly the way a real terminal session would. AGENTS.md/harness rule: tests must never
touch the repo's real `.env` -- every invocation here points `$POST_CORE_ENV_FILE` at a
temp file with fake values instead.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fake_env_file(tmp_path) -> Path:
    path = tmp_path / "fake.env"
    path.write_text("DEEPGRAM_API_KEY=sk-fake-not-a-real-key\n")
    return path


@pytest.fixture
def cli_env(fake_env_file) -> dict[str, str]:
    env = dict(os.environ)
    env["POST_CORE_ENV_FILE"] = str(fake_env_file)
    env["POST_CORE_EXTRA_NODE_TYPES"] = "fake_nodes:register"
    env["PYTHONPATH"] = os.pathsep.join(
        [str(FIXTURES_DIR), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    )
    return env


@pytest.fixture
def run_cli(cli_env):
    def _run(*args: str, timeout: float = 30.0, extra_env: dict | None = None) -> dict:
        env = dict(cli_env)
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(
            [sys.executable, "-m", "post_core.cli.main", *args],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise AssertionError(
                f"non-JSON stdout for {args!r} (exit {proc.returncode}): "
                f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
        return {"exit_code": proc.returncode, "stderr": proc.stderr, **payload}

    return _run


@pytest.fixture
def popen_cli(cli_env):
    def _popen(*args: str, extra_env: dict | None = None) -> subprocess.Popen:
        env = dict(cli_env)
        if extra_env:
            env.update(extra_env)
        return subprocess.Popen(
            [sys.executable, "-m", "post_core.cli.main", *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )

    return _popen


@pytest.fixture
def lavfi_clip(tmp_path) -> Path:
    """A tiny real media file via ffmpeg's `lavfi` synthetic source -- no footage fixture
    needed, and it is genuinely probeable (fps/duration/fingerprint) like a real clip."""
    out = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest",
         "-c:v", "libx264", "-c:a", "aac", str(out)],
        check=True, capture_output=True,
    )
    return out


@pytest.fixture
def ok_worker_script(tmp_path):
    """`ok_worker_script(name, out_name) -> cmd list[str]`: a real Python worker that speaks
    the `##POST` contract and always succeeds -- what `fake.cli_spend` nodes run."""

    def _make(name: str, out_name: str = "out.bin") -> list[str]:
        out_path = tmp_path / out_name
        script = tmp_path / f"{name}.py"
        script.write_text(textwrap.dedent(f"""
            import hashlib, json
            out = {str(out_path)!r}
            with open(out, "w") as f:
                f.write("payload:{name}")
            sha = hashlib.sha256(open(out, "rb").read()).hexdigest()
            print("##POST " + json.dumps({{"kind": "cost", "amount": 2.5, "unit": "usd"}}), flush=True)
            print("##POST " + json.dumps({{"kind": "artifact", "path": out, "role": "output", "sha256": sha}}), flush=True)
            print("##POST " + json.dumps({{"kind": "result", "ok": True, "detail": "done"}}), flush=True)
        """))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return [sys.executable, str(script)]

    return _make
