"""T36: terminal agents (Claude Code / Codex CLI) as read-only JSON oracles -- see
`terminal.py` and `docs/terminal-agents.md`."""
from __future__ import annotations

from .config import AgentChoice, choice_for, load_agents_config
from .errors import AgentBadJSON, AgentConfigError, AgentError, AgentFailed, AgentNotFound, AgentTimeout
from .terminal import ask_json

__all__ = [
    "ask_json", "choice_for", "load_agents_config", "AgentChoice", "AgentError", "AgentConfigError",
    "AgentNotFound", "AgentTimeout", "AgentFailed", "AgentBadJSON",
]
