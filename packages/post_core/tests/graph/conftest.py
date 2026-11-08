"""Shared fixtures: a small registry of fake compute node types for graph tests.

Real compute node types arrive in T12; these fakes stand in for "a node that produces a
video from an upstream video/prompt and may or may not spend money".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest
from pydantic import BaseModel, ConfigDict

from post_core.graph.registry import NodeRegistry, register_builtins
from post_core.graph.types import Cost, InputSpec, NodeType, OutputSpec


class GenerateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = ""
    seed: int = 0


def _estimate_generate_cost(params: GenerateParams) -> Optional[Cost]:
    return Cost(amount=1.5, unit="usd", provider="fake-provider")


# fake.generate: a spending compute node, one required "prompt" input, one "video" output.
FAKE_GENERATE = NodeType(
    id="fake.generate",
    kind="compute",
    inputs=(InputSpec(name="prompt", type="prompt", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenerateParams,
    spends=True,
    estimate_cost=_estimate_generate_cost,
)

# fake.transform: a free compute node, one required "video" input, one "video" output.
FAKE_TRANSFORM = NodeType(
    id="fake.transform",
    kind="compute",
    inputs=(InputSpec(name="video", type="video", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenerateParams,
    spends=False,
)

# fake.brand_consumer: a free compute node whose hash depends on the workflow's brand kit.
FAKE_BRAND_CONSUMER = NodeType(
    id="fake.brand_consumer",
    kind="compute",
    inputs=(InputSpec(name="video", type="video", required=True, many=False),),
    outputs=(OutputSpec(name="video", type="video"),),
    params_schema=GenerateParams,
    spends=False,
    uses_brand_kit=True,
)


@pytest.fixture
def registry() -> NodeRegistry:
    reg = NodeRegistry()
    register_builtins(reg)
    reg.register(FAKE_GENERATE)
    reg.register(FAKE_TRANSFORM)
    reg.register(FAKE_BRAND_CONSUMER)
    return reg


def _write_manifest(project_root: Path, node_type_id: str, input_hash: str, **extra) -> Path:
    from post_core.graph.state import artifact_dir

    directory = artifact_dir(project_root, node_type_id, input_hash)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"outputs": [], "finished_at": 0.0, **extra}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


@pytest.fixture
def write_manifest():
    """`write_manifest(project_root, node_type_id, input_hash, **extra) -> Path`."""
    return _write_manifest
