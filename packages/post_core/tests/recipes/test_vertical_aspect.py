"""T37: a beat takes its cut's aspect. A 4:5 cut on a video model that only offers 16:9 / 9:16
/ 1:1 (the T37 fixture) generates 9:16 and records `crop_to: 4:5`; the video worker crops it,
and `asset.verify` holds the result to 4:5 at the project's fps."""
from __future__ import annotations

import json

import pytest

from post_core.graph.hashing import compute_hashes
from post_core.graph.state import NodeState, artifact_dir, compute_states
from post_core.recipes import cmd_for as cmd_for_mod
from post_core.recipes import models
from post_core.recipes.instantiate import SpanSpec, add_more_stills, instantiate
from post_core.recipes.instantiate_extra import beat_aspects
from post_core.recipes.workers._common import probe_video

from conftest import enqueue_ready, run_to_completion

NTSC = "24000/1001"


def _params(workflow, node_id):
    return workflow.node(node_id).params


def test_t37_fixture_lists_model_aspects():
    assert "4:5" not in models.offered_aspects("kling3_0")
    assert "4:5" in models.offered_aspects("nano_banana_2")
    assert models.offered_aspects("no_such_model") is None


def test_4x5_cut_generates_nearest_covering_aspect_and_records_crop(project_root, kit):
    span = SpanSpec(id="b1", seconds=3.2, aspect="4:5", fps=NTSC, include_end_frame=True)
    wf = instantiate("live_action", span, kit, None, project_root)

    video = _params(wf, "b1-video")
    assert (video["aspect"], video["crop_to"], video["fps"]) == ("9:16", "4:5", NTSC)
    # Stills are the video's start/end frames: same aspect as the video, never cropped.
    for i in range(3):
        assert _params(wf, f"b1-still{i}")["aspect"] == "9:16"
    assert _params(wf, "b1-endframe")["aspect"] == "9:16"
    verify = _params(wf, "b1-verify")
    assert verify["expect_aspect"] == "4:5"
    assert verify["expect_fps"] == NTSC
    assert verify["min_seconds"] == pytest.approx(3.2)
    assert verify["allow_hold"] is False


@pytest.mark.parametrize("cut_aspect", ["9:16", "1:1", "16:9"])
def test_offered_aspect_instantiates_as_is(project_root, kit, cut_aspect):
    wf = instantiate("live_action", SpanSpec(id="b1", aspect=cut_aspect), kit, None, project_root)
    assert _params(wf, "b1-video")["aspect"] == cut_aspect
    assert _params(wf, "b1-video")["crop_to"] is None
    assert _params(wf, "b1-still0")["aspect"] == cut_aspect
    assert _params(wf, "b1-verify")["expect_aspect"] == cut_aspect


def test_still_model_choice_follows_the_video_aspect():
    assert beat_aspects("4:5") == beat_aspects("4:5", "kling3_0", "nano_banana_2")
    # A still model without 9:16 would still pick the frame nearest the video's aspect.
    plan = beat_aspects("9:16", still_model="no_such_model")
    assert (plan.still, plan.video, plan.crop_to) == ("9:16", "9:16", None)


def test_more_variants_keep_the_first_batch_aspect(project_root, kit):
    span = SpanSpec(id="b1", aspect="4:5", variants=2)
    wf = instantiate("live_action", span, kit, None, project_root)
    grown = add_more_stills(wf, SpanSpec(id="b1"), kit, None, 2)
    assert {n.params["aspect"] for n in grown.nodes if n.type_id == "still.generate"} == {"9:16"}


@pytest.mark.parametrize("hold_ok", [False, True])
def test_frozen_tail_check_follows_the_brief(project_root, registry, kit, hold_ok):
    wf = instantiate("live_action", SpanSpec(id="b1", aspect="4:5", fps=NTSC, hold_ok=hold_ok), kit, None, project_root)
    assert _params(wf, "b1-verify")["allow_hold"] is hold_ok
    wf.node("b1-pick").selected = next(e for e in wf.edges_into("b1-pick", "options")).id
    cmd_for = cmd_for_mod.make_cmd_for(wf, registry, project_root)
    verify_argv = cmd_for("b1-verify")
    assert ("--reject-frozen-tail" in verify_argv) is (not hold_ok)
    assert verify_argv[verify_argv.index("--expect-aspect") + 1] == "4:5"
    assert verify_argv[verify_argv.index("--expect-fps") + 1] == NTSC


def test_4x5_beat_end_to_end_is_cropped_and_verified(project_root, registry, kit):
    span = SpanSpec(id="b1", seconds=2.4, variants=1, aspect="4:5", fps=NTSC)
    wf = instantiate("live_action", span, kit, None, project_root)
    executor = run_to_completion(project_root, wf, registry)

    pick = wf.node("b1-pick")
    pick.selected = next(e for e in wf.edges_into("b1-pick", "options")).id
    cmd_for = cmd_for_mod.make_cmd_for(wf, registry, project_root)
    enqueue_ready(project_root, wf, registry, cmd_for, executor.authorization)
    for _ in range(25):
        if not executor.run_once():
            break

    hashes = compute_hashes(wf, registry)
    states = compute_states(wf, registry, project_root, hashes=hashes)
    assert states["b1-verify"] == NodeState.DONE, states
    assert states["b1-approve"] == NodeState.NEEDS_APPROVAL

    video_dir = artifact_dir(project_root, "video.generate", hashes["b1-video"])
    manifest = json.loads((video_dir / "manifest.json").read_text())
    main, generated = manifest["outputs"]
    assert (main["path"], main["generated_aspect"], main["crop_to"]) == ("video.mp4", "9:16", "4:5")
    assert generated["role"] == "generated"
    cropped = probe_video(video_dir / "video.mp4")
    assert cropped["width"] * 5 == cropped["height"] * 4
    assert (cropped["fps_num"], cropped["fps_den"]) == (24000, 1001)
    raw = probe_video(video_dir / "generated.mp4")
    assert raw["width"] * 16 == raw["height"] * 9

    from post_core.export._context import find_asset_for_node

    asset = find_asset_for_node(project_root, "b1-approve")
    assert asset is not None and (asset.fps.num, asset.fps.den) == (24000, 1001)
