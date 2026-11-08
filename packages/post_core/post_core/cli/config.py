"""Secrets and tool discovery for the CLI. AGENTS.md: "Secrets live in `.env` at the repo
root ... `post_core` loads it at startup without overriding real environment variables.
Never print, log, commit or echo key values."

`post doctor` is the only command that reports on any of this, and it only ever reports
booleans (present/absent) -- never a value, never even a prefix of one.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..store.paths import store_root

# Keys .env.example documents (kept in sync by hand -- there is no schema for this file).
KNOWN_ENV_KEYS = (
    "DEEPGRAM_API_KEY",
    "ELEVENLABS_API_KEY",
    "HEYGEN_API_KEY",
    "SYNC_API_KEY",
)

TOOLS = ("ffmpeg", "ffprobe")


def _repo_root() -> Path:
    """`<...>/post3` -- three levels up from this file
    (`packages/post_core/post_core/cli/config.py`)."""
    return Path(__file__).resolve().parents[4]


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def load_env(env_path: Optional[Path] = None, environ: Optional[dict] = None) -> dict[str, str]:
    """Load `<repo>/.env` (or `env_path`, or `$POST_CORE_ENV_FILE` if set -- tests point
    this at a temp file with fake values so a test run never opens the real `.env`) into
    `environ` (defaults to the real `os.environ`), never overriding a key that is already
    set for real. Returns the values read from the file (for `doctor`'s presence check
    only -- callers must never print this dict; it holds real secrets)."""
    import os

    if env_path is not None:
        target = env_path
    elif os.environ.get("POST_CORE_ENV_FILE"):
        target = Path(os.environ["POST_CORE_ENV_FILE"])
    else:
        target = _repo_root() / ".env"
    values = _parse_env_file(target)
    env = environ if environ is not None else os.environ
    for key, value in values.items():
        env.setdefault(key, value)
    return values


def load_project_config(project_root: str | Path) -> dict:
    """`<project>/.post3/config.json`, or `{}` if it doesn't exist yet. Project-local,
    non-secret settings only (e.g. default aspect ratio) -- never API keys."""
    path = store_root(project_root) / "config.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _tool_present(name: str) -> bool:
    return shutil.which(name) is not None


def providers_mode() -> str:
    """T31: `"fake"` when `POST3_FAKE_PROVIDERS=1` (placeholder media, nothing spends), else
    `"real"` -- generation calls real providers and spends credits."""
    from ..recipes.models import fake_mode

    return "fake" if fake_mode() else "real"


def doctor_report(project_root: Optional[str | Path] = None) -> dict:
    """Booleans only: which known keys are set (in the real environment, after `load_env`
    has run) and which external tools are on PATH. Never the values. Plus `providers`
    (`fake`|`real`), so every surface can say whether a click spends."""
    import os

    load_env()  # make sure .env's keys are visible before checking presence
    keys = {key: bool(os.environ.get(key)) for key in KNOWN_ENV_KEYS}
    tools = {name: _tool_present(name) for name in TOOLS}
    report = {"providers": providers_mode(), "keys": keys, "tools": tools}
    if project_root is not None:
        report["project_root"] = str(Path(project_root).resolve())
        report["project_initialised"] = store_root(project_root).is_dir()
    return report


__all__ = ["load_env", "load_project_config", "doctor_report", "providers_mode", "KNOWN_ENV_KEYS", "TOOLS"]
