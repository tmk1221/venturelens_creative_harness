"""Acceptance: the animation path fails on a brand-lint violation, and a fixed version
(different params -> a fresh input_hash) passes."""
from __future__ import annotations

from post_core.graph.hashing import compute_hashes
from post_core.graph.state import NodeState, compute_states
from post_core.recipes.instantiate import SpanSpec, instantiate

from conftest import run_to_completion


def test_animation_design_fails_lint_then_passes(project_root, registry, kit):
    bad_span = SpanSpec(id="beat-anim", instruction="a lower third", raw_css_injection="body{color:#123456;}")
    bad_workflow = instantiate("motion_graphic", bad_span, kit, None, project_root)
    run_to_completion(project_root, bad_workflow, registry)

    hashes = compute_hashes(bad_workflow, registry)
    states = compute_states(bad_workflow, registry, project_root, hashes=hashes)
    assert states["beat-anim-design"] == NodeState.FAILED

    good_span = SpanSpec(id="beat-anim", instruction="a lower third")  # no off-palette injection
    good_workflow = instantiate("motion_graphic", good_span, kit, None, project_root)
    run_to_completion(project_root, good_workflow, registry)

    hashes = compute_hashes(good_workflow, registry)
    states = compute_states(good_workflow, registry, project_root, hashes=hashes)
    assert states["beat-anim-design"] == NodeState.DONE
