"""Fake node types for driving the `post` CLI end to end (T06 acceptance test), loaded into
the CLI's registry via `$POST_CORE_EXTRA_NODE_TYPES=fake_nodes:register` -- the same
extension point a real T12 recipe module will use. Never touches a real provider.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from post_core.graph.types import Cost, InputSpec, NodeType, OutputSpec


class GenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    cmd: list[str] = []


def _cost(params: GenParams) -> Optional[Cost]:
    return Cost(amount=2.5, unit="usd", provider="fake-cli-provider")


FAKE_SPEND = NodeType(
    id="fake.cli_spend",
    kind="compute",
    inputs=(),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenParams,
    spends=True,
    lane="single",
    estimate_cost=_cost,
)


def register(registry) -> None:
    registry.register(FAKE_SPEND, replace=True)
