"""Acceptance: every recipe template instantiates to a valid workflow for a span, and
`plan()`'s cost total comes straight from the fixture pricing (never a real CLI call)."""
from __future__ import annotations

import pytest

from post_core.graph.hashing import compute_hashes
from post_core.graph.plan import plan as plan_fn
from post_core.graph.state import compute_states
from post_core.graph.workflow import assert_valid
from post_core.recipes.instantiate import SpanSpec, instantiate


def test_every_recipe_instantiates_to_a_valid_workflow(project_root, registry, kit, tmp_path):
    footage = tmp_path / "clip.mp4"
    from post_core.recipes.workers._common import placeholder_video

    placeholder_video(footage, "source", seconds=2.0)

    cases = {
        "live_action": SpanSpec(id="la", variants=2),
        "motion_graphic": SpanSpec(id="mg", instruction="a title card"),
        "overlay": SpanSpec(id="ov", path=str(footage)),
        "provided": SpanSpec(id="pv", path=str(footage)),
    }
    for recipe_id, span in cases.items():
        workflow = instantiate(recipe_id, span, kit, None, project_root)
        assert_valid(workflow, registry)  # raises WorkflowError if wiring/types are wrong


def test_live_action_plan_cost_from_fixtures(project_root, registry, kit):
    span = SpanSpec(id="beat1", seconds=4.0, variants=2)
    workflow = instantiate("live_action", span, kit, None, project_root)
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, project_root, hashes=hashes)
    plan = plan_fn(workflow, registry, states)

    assert plan.estimated_cost, "expected a non-empty cost estimate from fixture pricing"
    usd_credits = {c.provider: c.amount for c in plan.estimated_cost}
    # 2 still.generate at 2 credits/call each (real `generate cost nano_banana_2` at 2k, T18).
    assert usd_credits.get("higgsfield", 0) == 4.0
    assert set(plan.needs_authorization) == {"beat1-still0", "beat1-still1"}
