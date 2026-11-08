"""Fake node types for driving post_api end to end, loaded via
`$POST_CORE_EXTRA_NODE_TYPES=fake_nodes:register` -- the same extension point the post_core
CLI's own T06 acceptance test uses. Never touches a real provider."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from post_core.graph.types import Cost, NodeType, OutputSpec


class GenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    cmd: list[str] = []


def _cost(params: GenParams) -> Optional[Cost]:
    return Cost(amount=1.5, unit="usd", provider="fake-api-provider")


FAKE_SPEND = NodeType(
    id="fake.api_spend",
    kind="compute",
    inputs=(),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenParams,
    spends=True,
    lane="single",
    estimate_cost=_cost,
)

FAKE_FREE = NodeType(
    id="fake.api_free",
    kind="compute",
    inputs=(),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenParams,
    spends=False,
    lane="single",
)


def register(registry) -> None:
    registry.register(FAKE_SPEND, replace=True)
    registry.register(FAKE_FREE, replace=True)
