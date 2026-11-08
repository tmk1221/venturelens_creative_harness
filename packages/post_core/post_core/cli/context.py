"""Shared plumbing every command needs: which project, which node-type registry, how to
turn a node id into the worker command line the executor should run.

Node types (image/video/audio generation) are wired as workflow-graph node types by T12,
which does not exist yet. Real recipes will register their node types into the registry the
same way `graph.registry.register_builtins` does. Until then (and for this task's own
acceptance test, which drives the CLI end to end against *fake* node types/workers), the
CLI supports registering extra node types via `$POST_CORE_EXTRA_NODE_TYPES`: a
comma-separated list of `module:function` specs, each imported and called as
`function(registry)`. A real deployment leaves this unset and gets exactly the builtins;
tests set it to point at fixture node types the way a future T12 recipe module will.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Optional

from .. import store as store_mod
from ..graph.registry import NodeRegistry, register_builtins
from ..graph.workflow import Node, Workflow
from ..store.paths import store_root
from .output import CLIError

EXTRA_NODE_TYPES_ENV = "POST_CORE_EXTRA_NODE_TYPES"


def resolve_project_root(raw: Optional[str]) -> Path:
    root = Path(raw).resolve() if raw else Path.cwd()
    if not store_root(root).is_dir():
        raise CLIError(f"{root}: not a post3 project (run `post init {root}` first)")
    return root


def build_registry() -> NodeRegistry:
    from ..ingest.transcribe import job as transcribe_job  # local: it imports the queue

    registry = NodeRegistry()
    register_builtins(registry)
    transcribe_job.register(registry)  # T35: so `post run`/`queue serve` can drive a transcription too
    spec_list = os.environ.get(EXTRA_NODE_TYPES_ENV, "")
    for spec in filter(None, (s.strip() for s in spec_list.split(","))):
        if ":" not in spec:
            raise CLIError(f"{EXTRA_NODE_TYPES_ENV}: bad spec {spec!r}, want 'module:function'")
        module_name, func_name = spec.split(":", 1)
        try:
            module = importlib.import_module(module_name)
            func = getattr(module, func_name)
        except (ImportError, AttributeError) as exc:
            raise CLIError(f"{EXTRA_NODE_TYPES_ENV}: cannot load {spec!r}: {exc}") from exc
        func(registry)
    return registry


def cmd_for(workflow: Workflow, node_id: str) -> list[str]:
    """The worker command line for `node_id`. T12's real compute node types will carry
    their own command-building logic; until then the convention is a `cmd` entry in the
    node's own params (a list of strings) -- what this task's fake node types/workers use."""
    node = workflow.node(node_id)
    if node.type_id == "transcript.transcribe":  # T35: builds its own worker argv
        from ..ingest.transcribe import job as transcribe_job

        return transcribe_job.build_cmd(workflow, node_id)
    cmd = node.params.get("cmd")
    if not isinstance(cmd, list) or not cmd:
        raise CLIError(
            f"node {node_id!r} (type {node.type_id!r}) has no params['cmd'] worker command "
            "-- real recipe node types (T12) will supply this automatically"
        )
    return [str(c) for c in cmd]


def node_from_json(data: dict) -> Node:
    return Node.model_validate(data)


# T12 carry-over #1: "workflow" is now a real `store.store` kind (KIND_MODELS resolves it
# via a local import to dodge a store<->graph import cycle -- see store/store.py), so the
# CLI no longer keeps a private copy of the atomic-envelope persistence logic; it is a thin
# pass-through to `store.write`/`store.read`, same as every other kind.
def save_workflow(project_root, workflow: Workflow, expected_rev: int) -> int:
    return store_mod.write(project_root, "workflow", workflow, expected_rev)


def load_workflow(project_root, workflow_id: str) -> tuple[Workflow, int]:
    return store_mod.read(project_root, "workflow", workflow_id)  # type: ignore[return-value]


__all__ = [
    "resolve_project_root", "build_registry", "cmd_for", "node_from_json",
    "save_workflow", "load_workflow", "EXTRA_NODE_TYPES_ENV",
]
