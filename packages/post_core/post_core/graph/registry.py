"""NodeType registry: register/get, plus the built-in node types.

Each test gets its own `NodeRegistry` (via `builtin_registry()` or a bare `NodeRegistry()`
plus its own `register()` calls for fakes) so registering a fake compute type in one test
never leaks into another. Real compute types (image/video generation, etc.) arrive in T12.
"""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict

from .lanes import DEFAULT_LANES, UnknownLane
from .types import InputSpec, NodeType, NoParams, OutputSpec


class UnknownNodeType(KeyError):
    def __init__(self, type_id: str) -> None:
        self.type_id = type_id
        super().__init__(f"no node type registered for {type_id!r}")


class NodeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, NodeType] = {}

    def register(self, node_type: NodeType, *, replace: bool = False) -> None:
        if not replace and node_type.id in self._types:
            raise ValueError(f"node type {node_type.id!r} already registered")
        if node_type.lane not in DEFAULT_LANES:
            raise UnknownLane(node_type.id, node_type.lane)  # no executor would ever run it
        self._types[node_type.id] = node_type

    def get(self, type_id: str) -> NodeType:
        try:
            return self._types[type_id]
        except KeyError:
            raise UnknownNodeType(type_id) from None

    def __contains__(self, type_id: str) -> bool:
        return type_id in self._types

    def all(self) -> Iterable[NodeType]:
        return tuple(self._types.values())


# --- built-ins -----------------------------------------------------------------------
# Real compute node types (image/video/audio generation) come in T12. These four are the
# structural primitives the graph needs to be usable at all: a literal file on disk, a
# literal text/prompt value, and the two human-in-the-loop gates.

class SourceFileParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    handle_type: str = "video"


class TextPromptParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


SOURCE_FILE = NodeType(
    id="source.file",
    kind="source",
    inputs=(),
    outputs=(OutputSpec(name="file", type="video"),),
    params_schema=SourceFileParams,
)

TEXT_PROMPT = NodeType(
    id="text.prompt",
    kind="source",
    inputs=(),
    outputs=(OutputSpec(name="text", type="prompt"),),
    params_schema=TextPromptParams,
)

HUMAN_PICK = NodeType(
    id="human.pick",
    kind="pick",
    inputs=(InputSpec(name="options", type="any", required=True, many=True),),
    outputs=(OutputSpec(name="chosen", type="any"),),
    params_schema=NoParams,
)

HUMAN_APPROVE = NodeType(
    id="human.approve",
    kind="approve",
    inputs=(InputSpec(name="subject", type="any", required=True, many=False),),
    outputs=(OutputSpec(name="approved", type="any"),),
    params_schema=NoParams,
)

BUILTINS = (SOURCE_FILE, TEXT_PROMPT, HUMAN_PICK, HUMAN_APPROVE)


def register_builtins(registry: NodeRegistry) -> None:
    for node_type in BUILTINS:
        registry.register(node_type, replace=True)


def builtin_registry() -> NodeRegistry:
    registry = NodeRegistry()
    register_builtins(registry)
    return registry
