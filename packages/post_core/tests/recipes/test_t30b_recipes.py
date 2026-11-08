"""T30b: overlay.place (behind/in_front branches), end frame, "+3 more", continuity edges,
brief.write's fuller fake brief, and the aroll_regenerate stub + consent gate."""
from __future__ import annotations

from post_core.graph import approvals as approvals_mod
from post_core.graph.hashing import compute_hashes
from post_core.graph.state import NodeState, compute_states
from post_core.graph.workflow import assert_valid
from post_core.recipes import consent as consent_mod
from post_core.recipes.instantiate import SpanSpec, add_more_stills, instantiate
from post_core.recipes.prompts import recommend_end_frame
from post_core.recipes.workers._common import placeholder_video

from conftest import run_to_completion


def _footage(tmp_path):
    path = tmp_path / "clip.mp4"
    placeholder_video(path, "source", seconds=2.0)
    return path


# ---- overlay.place ------------------------------------------------------------------------

def test_overlay_in_front_skips_measure_and_cutout(project_root, registry, kit, tmp_path):
    footage = _footage(tmp_path)
    span = SpanSpec(id="ov", path=str(footage), overlay_depth="in_front", overlay_position="lower-band")
    workflow = instantiate("overlay", span, kit, None, project_root)
    assert_valid(workflow, registry)
    type_ids = {n.type_id for n in workflow.nodes}
    assert "overlay.measure" not in type_ids
    assert "overlay.cutout" not in type_ids
    assert "overlay.place" in type_ids
    place = workflow.node("ov-place")
    assert place.params["depth"] == "in_front"
    assert place.params["position"] == "lower-band"
    # place is wired straight off provided.clip
    assert any(e.from_node == "ov-provided" and e.to_node == "ov-place" for e in workflow.edges)


def test_overlay_behind_wires_measure_and_cutout_into_place(project_root, registry, kit, tmp_path):
    footage = _footage(tmp_path)
    span = SpanSpec(id="ov", path=str(footage), overlay_depth="behind", overlay_position="full-frame")
    workflow = instantiate("overlay", span, kit, None, project_root)
    assert_valid(workflow, registry)
    type_ids = {n.type_id for n in workflow.nodes}
    assert {"overlay.measure", "overlay.cutout", "overlay.place"} <= type_ids
    assert any(e.from_node == "ov-cutout" and e.to_node == "ov-place" for e in workflow.edges)


def test_overlay_place_param_change_marks_downstream_stale(project_root, registry, kit, tmp_path):
    footage = _footage(tmp_path)
    span_a = SpanSpec(id="ov", path=str(footage), overlay_depth="in_front", overlay_position="lower-band")
    wf_a = instantiate("overlay", span_a, kit, None, project_root)
    hashes_a = compute_hashes(wf_a, registry)

    span_b = SpanSpec(id="ov", path=str(footage), overlay_depth="in_front", overlay_position="right")
    wf_b = instantiate("overlay", span_b, kit, None, project_root)
    hashes_b = compute_hashes(wf_b, registry)

    assert hashes_a["ov-place"] != hashes_b["ov-place"]
    assert hashes_a["ov-verify"] != hashes_b["ov-verify"]
    assert hashes_a["ov-approve"] != hashes_b["ov-approve"]


# NOTE: no run_to_completion test drains the overlay recipe's queue end to end here -- doing
# so exposes a pre-existing T12 gap unrelated to T30b: `provided.clip`'s artifact is a
# `pointer.json` (AGENTS.md: never copy/move live footage), but `overlay.cutout`/`overlay.
# place`'s `cmd_for` wiring resolves its "video" input straight to that pointer file rather
# than the real path it names, so ffmpeg/ffprobe fail on it -- true before this slice too
# (nothing ever ran the overlay recipe's queue to completion). Left as-is per AGENTS.md
# ("shared generator scripts... isolate script changes separately"); flagged in the handoff.


# ---- end frame ------------------------------------------------------------------------------

def test_recommend_end_frame_heuristic():
    assert recommend_end_frame("The workspace transforms from cluttered to calm.")
    assert not recommend_end_frame("We reviewed the roadmap together.")


def test_live_action_includes_end_frame_when_requested(project_root, registry, kit):
    span = SpanSpec(id="la", variants=2, include_end_frame=True, end_frame_prompt="a tidy desk")
    workflow = instantiate("live_action", span, kit, None, project_root)
    assert_valid(workflow, registry)
    assert workflow.node("la-endframe").type_id == "endframe.generate"
    assert any(e.from_node == "la-pick" and e.to_node == "la-endframe" for e in workflow.edges)
    assert any(e.from_node == "la-endframe" and e.to_node == "la-video" and e.to_input == "end_image"
               for e in workflow.edges)


def test_live_action_omits_end_frame_by_default(project_root, registry, kit):
    span = SpanSpec(id="la", variants=1)
    workflow = instantiate("live_action", span, kit, None, project_root)
    assert not any(n.type_id == "endframe.generate" for n in workflow.nodes)


# ---- "+3 more" --------------------------------------------------------------------------------

def test_add_more_stills_shares_the_same_pick(project_root, registry, kit):
    span = SpanSpec(id="la", variants=2)
    workflow = instantiate("live_action", span, kit, None, project_root)
    original_still_ids = {n.id for n in workflow.nodes if n.type_id == "still.generate"}
    assert original_still_ids == {"la-still0", "la-still1"}

    grown = add_more_stills(workflow, span, kit, None, 3)
    assert_valid(grown, registry)
    new_still_ids = {n.id for n in grown.nodes if n.type_id == "still.generate"}
    assert new_still_ids == {"la-still0", "la-still1", "la-still2", "la-still3", "la-still4"}
    options_edges = grown.edges_into("la-pick", "options")
    assert {e.from_node for e in options_edges} == new_still_ids


# ---- continuity ---------------------------------------------------------------------------

def test_continuity_source_wires_a_source_file_node_into_every_still(project_root, registry, kit, tmp_path):
    frame = tmp_path / "prior_pick.png"
    frame.write_bytes(b"not a real png but a stand-in path")
    span = SpanSpec(id="la2", variants=2, continuity_source_path=str(frame))
    workflow = instantiate("live_action", span, kit, None, project_root)
    assert_valid(workflow, registry)
    source_node = workflow.node("la2-continuity-source")
    assert source_node.params["path"] == str(frame)
    continuity_edges = [e for e in workflow.edges if e.from_node == "la2-continuity-source"]
    assert {e.to_node for e in continuity_edges} == {"la2-still0", "la2-still1"}
    assert all(e.to_input == "continuity" for e in continuity_edges)


# ---- brief.write fake mode ----------------------------------------------------------------

def test_brief_write_fake_mode_composes_from_words_and_context(project_root, registry, kit):
    span = SpanSpec(
        id="mg", instruction="a title card", words_text="we grew revenue forty percent",
        direction_note="open with the number", writer_context={"identity": "bold and precise"},
    )
    workflow = instantiate("motion_graphic", span, kit, None, project_root)
    run_to_completion(project_root, workflow, registry, max_cycles=2)
    hashes = compute_hashes(workflow, registry)
    from post_core.graph.state import artifact_dir

    directory = artifact_dir(project_root, "brief.write", hashes["mg-brief"])
    text = (directory / "brief.txt").read_text(encoding="utf-8")
    assert "open with the number" in text
    assert "forty percent" in text
    assert "bold and precise" in text


def test_brief_write_fake_mode_falls_back_to_plain_instruction(project_root, registry, kit):
    span = SpanSpec(id="mg", instruction="a title card")
    workflow = instantiate("motion_graphic", span, kit, None, project_root)
    run_to_completion(project_root, workflow, registry, max_cycles=2)
    hashes = compute_hashes(workflow, registry)
    from post_core.graph.state import artifact_dir

    directory = artifact_dir(project_root, "brief.write", hashes["mg-brief"])
    text = (directory / "brief.txt").read_text(encoding="utf-8")
    assert text == "a title card"


# ---- aroll_regenerate + consent.gate --------------------------------------------------------

def test_aroll_regenerate_consent_gate_needs_human_with_no_consent_record(project_root, registry, kit):
    span = SpanSpec(id="regen", regen_mode="fix_line", instruction="fix the stumble at 00:42")
    workflow = instantiate("aroll_regenerate", span, kit, None, project_root)
    assert_valid(workflow, registry)
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, project_root, hashes=hashes)
    assert states["regen-consent"] == NodeState.NEEDS_APPROVAL


def test_aroll_regenerate_consent_gate_auto_approved_once_consent_recorded(project_root, registry, kit):
    consent_mod.record_consent(project_root, presenter="Presenter", release_path="releases/presenter.pdf", date="2026-09-22")
    span = SpanSpec(id="regen", regen_mode="alternate_opening")
    workflow = instantiate("aroll_regenerate", span, kit, None, project_root)
    hashes = compute_hashes(workflow, registry)
    states = compute_states(workflow, registry, project_root, hashes=hashes)
    assert states["regen-consent"] == NodeState.DONE
    assert approvals_mod.is_approved(project_root, hashes["regen-consent"])
