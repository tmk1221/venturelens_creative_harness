"""Handle types and node-type declarations for the build graph.

A NodeType is the *kind* of node (e.g. ``source.file``); a Workflow's individual Node
instances (workflow.py) reference a NodeType by ``type_id`` and carry their own params.
NodeTypes live in a NodeRegistry (registry.py) and are never imported by id elsewhere, so
compute types (T12) can be registered later without this module knowing about them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict

HandleType = Literal[
    "image", "video", "audio", "prompt", "text", "character", "brand", "words",
]

# Pseudo-type accepted only by generic pass-through node types (human.pick, human.approve):
# a handle declared "any" is compatible with every concrete HandleType.
ANY_TYPE: Literal["any"] = "any"

Kind = Literal["compute", "pick", "approve", "source"]


class NoParams(BaseModel):
    """Empty params schema for node types that take none."""

    model_config = ConfigDict(extra="forbid")


class Cost(BaseModel):
    """An estimated (or, later, recorded) spend. Mirrors the worker contract's `cost` event."""

    model_config = ConfigDict(extra="forbid")

    amount: float
    unit: str = "usd"
    provider: Optional[str] = None


@dataclass(frozen=True)
class InputSpec:
    name: str
    type: str  # a HandleType, or ANY_TYPE
    required: bool = True
    many: bool = False


@dataclass(frozen=True)
class OutputSpec:
    name: str
    type: str  # a HandleType, or ANY_TYPE


def _default_check(artifact_dir: Path) -> bool:
    """A node type with no custom `check` is satisfied by manifest.json alone."""
    return (artifact_dir / "manifest.json").is_file()


def _no_cost(params: BaseModel) -> Optional[Cost]:
    return None


@dataclass(frozen=True)
class NodeType:
    """One node kind's static declaration. Instances of it are `workflow.Node`."""

    id: str
    inputs: tuple[InputSpec, ...] = ()
    outputs: tuple[OutputSpec, ...] = ()
    params_schema: type[BaseModel] = NoParams
    kind: Kind = "compute"
    spends: bool = False
    lane: str = "default"
    # Cross-process exclusive resources this node's worker needs held for its whole run
    # (e.g. "resolve" -- DaVinci Resolve's scripting API is one mutable connection; two
    # workers touching it at once interleave instead of colliding loudly). Additive to
    # `lane`, which only controls *concurrency*: a node can share a lane with others and
    # still need a resource lock, or need no resource at all (the common case, `()`).
    resources: tuple[str, ...] = ()
    version: int = 1
    # Whether this node's hash (and thus artifact identity) depends on the workflow's
    # brand_kit_hash. Most node types don't touch brand assets, so this defaults off.
    uses_brand_kit: bool = False
    estimate_cost: Callable[[BaseModel], Optional[Cost]] = _no_cost
    check: Callable[[Path], bool] = _default_check

    def input(self, name: str) -> InputSpec:
        for spec in self.inputs:
            if spec.name == name:
                return spec
        raise KeyError(f"{self.id}: no input {name!r}")

    def output(self, name: str) -> OutputSpec:
        for spec in self.outputs:
            if spec.name == name:
                return spec
        raise KeyError(f"{self.id}: no output {name!r}")


def types_compatible(a: str, b: str) -> bool:
    return a == b or a == ANY_TYPE or b == ANY_TYPE
