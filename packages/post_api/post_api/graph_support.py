"""T26: a node registry + cmd_for that know about *both* T12's real recipe node types
(`still.generate`, `video.generate`, ...) and the test-only fake node types some existing
tests register via `$POST_CORE_EXTRA_NODE_TYPES` (`post_core.cli.context.build_registry`).

`workflows.py`'s generic `/workflows` routes and `runtime.py`'s background drain loop both
used to call `cli.context.build_registry`/`cli.context.cmd_for` directly -- fine for the
fake node types those routes were built against, but real recipe-instantiated workflows
(T26's span-attached graphs) carry node types like `still.generate` that registry never
knew about, and a real recipe node's params never has the `cmd`-list convention `cli.
context.cmd_for` reads. This module is the one place both concerns are merged, so every
caller (workflows.py, runtime.py, routes/enrich.py) sees the same picture of "every node
type this app can run right now."
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from post_core.cli.context import build_registry as _cli_build_registry
from post_core.graph.registry import NodeRegistry
from post_core.graph.workflow import Workflow
from post_core.ingest.transcribe import job as transcribe_job
from post_core.recipes import full_registry as _recipe_full_registry
from post_core.recipes.cmd_for import make_cmd_for as _recipe_make_cmd_for


def combined_registry() -> NodeRegistry:
    """Builtins + every T12 recipe node type + whatever `$POST_CORE_EXTRA_NODE_TYPES` adds
    (test fakes) -- the union every route/background loop should plan and run against."""
    registry = _recipe_full_registry()
    extra = _cli_build_registry()
    for node_type in extra.all():
        if node_type.id not in registry:
            registry.register(node_type)
    return registry


def combined_cmd_for(workflow: Workflow, registry: NodeRegistry, project_root: str | Path) -> Callable[[str], list]:
    """A node's worker argv: the recipe-package builder for real T12 node types (dynamic --
    resolves upstream artifact paths at call time), falling back to the legacy `params['cmd']`
    convention fake/test node types still use."""
    recipe_cmd_for = _recipe_make_cmd_for(workflow, registry, project_root)

    def _cmd_for(node_id: str) -> list[str]:
        node = workflow.node(node_id)
        if node.type_id == transcribe_job.TYPE_ID:  # T35: a queued transcription builds its own argv
            return transcribe_job.build_cmd(workflow, node_id)
        cmd = node.params.get("cmd") if isinstance(node.params, dict) else None
        if isinstance(cmd, list) and cmd:
            return [str(c) for c in cmd]
        return recipe_cmd_for(node_id)

    return _cmd_for


__all__ = ["combined_registry", "combined_cmd_for"]
