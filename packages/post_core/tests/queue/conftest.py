"""Shared fixtures for queue/executor tests: a tiny registry of fake compute node types.
Real (subprocess) fake workers live in `worker_scripts.py`, imported directly by test
modules -- kept out of this file, and this directory has no `__init__.py`, so nothing here
is ever importable as a top-level `queue` package shadowing the stdlib `queue` module that
`workers/runner.py` depends on.
"""
from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel, ConfigDict

from post_core.graph.registry import NodeRegistry, register_builtins
from post_core.graph.types import Cost, InputSpec, NodeType, OutputSpec


class GenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""


def _cost(params: GenParams) -> Optional[Cost]:
    return Cost(amount=1.5, unit="usd", provider="fake-provider")


# A spending compute node in the "remote" lane (default lanes: remote=8).
FAKE_SPEND = NodeType(
    id="fake.spend",
    kind="compute",
    inputs=(InputSpec(name="text", type="prompt", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenParams,
    spends=True,
    lane="remote",
    estimate_cost=_cost,
)

# A spending compute node in the "single" lane -- runs strictly one at a time, so a budget
# test can observe a still-`queued` sibling job between two `run_once()` calls.
FAKE_SPEND_SINGLE = NodeType(
    id="fake.spend_single",
    kind="compute",
    inputs=(InputSpec(name="text", type="prompt", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenParams,
    spends=True,
    lane="single",
    estimate_cost=_cost,
)

# A free compute node in the "single" lane (default lanes: single=1 -- good for testing
# lane concurrency limits deterministically).
FAKE_FREE = NodeType(
    id="fake.free",
    kind="compute",
    inputs=(InputSpec(name="video", type="video", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenParams,
    spends=False,
    lane="single",
)

# A free compute node in the "render" lane that also declares the "resolve" resource (T06
# carry-over #3: `resources`, not a magic lane name), for the cross-process resource-lock
# test. Two of these can run in the same lane concurrently but must never hold the
# "resolve" resource lock at the same time.
FAKE_RESOLVE = NodeType(
    id="fake.resolve",
    kind="compute",
    inputs=(InputSpec(name="video", type="video", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenParams,
    spends=False,
    lane="render",
    resources=("resolve",),
)


@pytest.fixture
def registry() -> NodeRegistry:
    reg = NodeRegistry()
    register_builtins(reg)
    reg.register(FAKE_SPEND)
    reg.register(FAKE_SPEND_SINGLE)
    reg.register(FAKE_FREE)
    reg.register(FAKE_RESOLVE)
    return reg
