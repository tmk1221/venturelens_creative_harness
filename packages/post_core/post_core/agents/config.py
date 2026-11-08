"""T36: which terminal agent (and model) runs each operation -- `<project>/.post3/agents.json`.

    {
      "default":           {"provider": "claude", "model": null, "timeout_seconds": 420},
      "suggest_visuals":   {"provider": "codex"},
      "motion_from_frame": {"model": "sonnet"}
    }

Every key is optional. An operation's entry is laid over `default`, which is laid over the
built-in defaults (provider `claude`, the CLI's own default model, 420 s). No file means
every operation runs on `claude` with its default model. There is no implicit fallback from
one provider to another: if the chosen CLI is missing or fails, the call fails.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..store.paths import store_root
from .errors import AgentConfigError

AGENTS_FILE = "agents.json"
PROVIDERS = ("claude", "codex")
OPERATIONS = ("suggest_visuals", "brief_write", "motion_from_frame")
DEFAULT_PROVIDER = "claude"
DEFAULT_TIMEOUT_SECONDS = 420.0
_FIELDS = {"provider", "model", "timeout_seconds"}


@dataclass(frozen=True)
class AgentChoice:
    operation: str
    provider: str
    model: Optional[str]
    timeout_seconds: float

    @property
    def label(self) -> str:
        return f"{self.provider} / {self.model or 'CLI default'}"


def agents_path(project_root: str | Path) -> Path:
    return store_root(project_root) / AGENTS_FILE


def load_agents_config(project_root: Optional[str | Path]) -> dict:
    """The project's `agents.json` as a dict, `{}` when there is none (or no project)."""
    if project_root is None:
        return {}
    path = agents_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise AgentConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AgentConfigError(f"{path} must hold a JSON object")
    return data


def _entry(data: dict, key: str, path_hint: str) -> dict:
    entry = data.get(key, {})
    if not isinstance(entry, dict):
        raise AgentConfigError(f"{path_hint}: {key!r} must be an object")
    unknown = set(entry) - _FIELDS
    if unknown:
        raise AgentConfigError(f"{path_hint}: {key!r} has unknown field(s) {sorted(unknown)}")
    return entry


def choice_for(operation: str, project_root: Optional[str | Path] = None) -> AgentChoice:
    """The provider/model/timeout `operation` runs with in this project."""
    if operation not in OPERATIONS:
        raise AgentConfigError(f"unknown agent operation {operation!r}; known: {', '.join(OPERATIONS)}")
    data = load_agents_config(project_root)
    hint = AGENTS_FILE
    unknown_keys = set(data) - {"default", *OPERATIONS}
    if unknown_keys:
        raise AgentConfigError(f"{hint}: unknown key(s) {sorted(unknown_keys)}; use 'default' or {', '.join(OPERATIONS)}")
    merged = {**_entry(data, "default", hint), **_entry(data, operation, hint)}
    provider = merged.get("provider") or DEFAULT_PROVIDER
    if provider not in PROVIDERS:
        raise AgentConfigError(f"{hint}: unknown provider {provider!r} for {operation}; choose claude or codex")
    model = merged.get("model") or None
    timeout = merged.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise AgentConfigError(f"{hint}: timeout_seconds for {operation} must be a positive number")
    return AgentChoice(operation=operation, provider=provider, model=model, timeout_seconds=float(timeout))


__all__ = [
    "AGENTS_FILE", "PROVIDERS", "OPERATIONS", "DEFAULT_PROVIDER", "DEFAULT_TIMEOUT_SECONDS",
    "AgentChoice", "agents_path", "load_agents_config", "choice_for",
]
