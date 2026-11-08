"""T12: recipe node types, prompt/cost wiring, cast registry, and templates over the
existing Higgsfield / HyperFrames generators, speaking the T03 worker contract.

`register(registry)` wires every node type this package declares into a `NodeRegistry`
(the same pattern `graph.registry.register_builtins` uses) -- callers add it the way the
CLI's `POST_CORE_EXTRA_NODE_TYPES` mechanism (`cli/context.py`) expects, or call it
directly in-process (tests, `post_api`).
"""
from __future__ import annotations

from ..graph.registry import NodeRegistry, register_builtins
from .node_types import RECIPE_NODE_TYPES


def register(registry: NodeRegistry) -> None:
    for node_type in RECIPE_NODE_TYPES:
        registry.register(node_type, replace=True)


def full_registry() -> NodeRegistry:
    """The builtins (`human.pick`/`human.approve`/...) plus every T12 recipe node type --
    every recipe graph `instantiate.py` builds uses both."""
    registry = NodeRegistry()
    register_builtins(registry)
    register(registry)
    return registry


__all__ = ["register", "full_registry", "RECIPE_NODE_TYPES"]
