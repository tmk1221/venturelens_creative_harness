"""T36: what can go wrong calling a terminal agent, as distinct exception types so a worker,
the API and the CLI can each say exactly which thing failed (`reason`) without matching on
prose. Every one is an `AgentError` (a `RuntimeError`), and no failure ever writes output:
the caller only writes after a reply has been parsed and validated."""
from __future__ import annotations


class AgentError(RuntimeError):
    """A terminal-agent call failed; nothing was applied."""

    reason = "failed"


class AgentConfigError(AgentError):
    """`.post3/agents.json` is unreadable, or names an unknown provider/operation."""

    reason = "config"


class AgentNotFound(AgentError):
    """The provider's CLI is not on PATH (or not at the configured path)."""

    reason = "not_found"


class AgentTimeout(AgentError):
    """The agent did not finish within the operation's timeout; its process group was killed."""

    reason = "timeout"


class AgentFailed(AgentError):
    """The agent exited non-zero (e.g. a usage limit); the message carries its stderr tail."""

    reason = "failed"


class AgentBadJSON(AgentError):
    """The agent's final message was not one JSON object."""

    reason = "bad_json"


__all__ = ["AgentError", "AgentConfigError", "AgentNotFound", "AgentTimeout", "AgentFailed", "AgentBadJSON"]
