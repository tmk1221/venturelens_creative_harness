"""T18 item 4: a "default" lane (limit 2) so a node type left at `NodeType.lane`'s default is
scheduled, and the registry rejects a lane no executor runs."""
from __future__ import annotations

import pytest

from post_core.graph.lanes import DEFAULT_LANES, UnknownLane
from post_core.graph.registry import NodeRegistry
from post_core.graph.types import NodeType, OutputSpec
from post_core.queue import DEFAULT_LANES as QUEUE_LANES
from post_core.queue.executor import Executor


def test_default_lane_exists_with_limit_two():
    assert DEFAULT_LANES["default"] == 2
    assert QUEUE_LANES is DEFAULT_LANES
    assert NodeType(id="x").lane in DEFAULT_LANES


def test_executor_runs_the_default_lane():
    assert Executor.__dataclass_fields__["lanes"].default_factory()["default"] == 2


def test_registry_accepts_every_known_lane():
    reg = NodeRegistry()
    for lane in DEFAULT_LANES:
        reg.register(NodeType(id=f"t.{lane}", lane=lane, outputs=(OutputSpec(name="o", type="any"),)))
    assert len(tuple(reg.all())) == len(DEFAULT_LANES)


def test_registry_rejects_unknown_lane():
    reg = NodeRegistry()
    with pytest.raises(UnknownLane, match="'gpu'"):
        reg.register(NodeType(id="t.gpu", lane="gpu"))
    assert "t.gpu" not in reg
