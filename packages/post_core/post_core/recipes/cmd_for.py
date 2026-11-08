"""`make_cmd_for(workflow, registry, project_root) -> CmdFor`: the recipe package's own
worker-argv builder, passed to `queue.executor.Executor(cmd_for=...)` in place of the CLI's
generic `cli.context.cmd_for` (which only reads a static `node.params['cmd']`).

It has to be dynamic, not static, because a node downstream of a `human.pick` (e.g.
`motion.from_frame`'s `frame` input, or `video.generate`'s `start_image`) has no resolvable
file path until the pick is actually made -- which happens after the workflow is built.
`queue.enqueue` only calls `cmd_for(node_id)` once a node is `READY` (T05), by which point
every upstream pick/approve on its path is already resolved, so resolving paths *here*,
from the current `graph.hashing.compute_hashes` + `graph.state.artifact_dir`, is always
safe. `pick`/`approve` nodes have no artifact_dir of their own (T04: only `compute` nodes
get jobs) -- `_resolve_producer` walks through them to the real upstream compute node.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..graph.hashing import compute_hashes
from ..graph.registry import NodeRegistry
from ..graph.state import artifact_dir
from ..graph.workflow import Workflow
from .cmd import build_cmd

# One primary output filename per node type -- the convention every recipe worker's `--out`
# default follows (see `recipes/workers/*.py`). `animation.design`'s own artifact_dir IS a
# (flat) composition directory, not one named file -- see `DIR_OUTPUTS` below.
OUTPUT_FILENAME: dict[str, str] = {
    "still.generate": "image.png",
    "endframe.generate": "endframe.png",
    "video.generate": "video.mp4",
    "motion.from_frame": "motion_prompt.txt",
    "brief.write": "brief.txt",
    "animation.draft_render": "draft.mp4",
    "animation.render": "output.mp4",
    "overlay.cutout": "output.mp4",
    "overlay.measure": "measurements.json",
    "overlay.place": "output.mp4",
    "aroll.regenerate": "request.json",
    "provided.clip": "pointer.json",
}
DIR_OUTPUTS = {"animation.design"}


def _resolve_producer(workflow: Workflow, node_id: str) -> str:
    """Follow `pick.selected` / `approve`'s single incoming edge until landing on the real
    upstream compute (or, in principle, source) node id."""
    node = workflow.node(node_id)
    if node.type_id == "human.pick":
        if node.selected is None:
            raise ValueError(f"{node_id}: pick not made yet")
        edge = next(e for e in workflow.edges_into(node_id, "options") if e.id == node.selected)
        return _resolve_producer(workflow, edge.from_node)
    if node.type_id == "human.approve":
        edges = workflow.edges_into(node_id, "subject")
        if not edges:
            raise ValueError(f"{node_id}: approve node has no wired subject")
        return _resolve_producer(workflow, edges[0].from_node)
    return node_id


class UnresolvedUpstream(ValueError):
    """An upstream node this command needs a file/dir from has no resolved input_hash yet
    (e.g. an un-made pick still further upstream) -- `queue.enqueue` should never call
    `cmd_for` for a node in this state (T05: only `READY` nodes are enqueued), so this is a
    programming-error guard, not an expected runtime path."""


def _producer_path(
    workflow: Workflow, registry: NodeRegistry, hashes: dict, project_root: str | Path, node_id: str,
) -> Path:
    producer_id = _resolve_producer(workflow, node_id)
    producer = workflow.node(producer_id)
    # `source.file` (T26 graph view's "+ reference image" palette node) is a `kind="source"`
    # builtin, not a T12 recipe compute node -- it never gets an artifact_dir/manifest of its
    # own (nothing in T02-T11 ever marks a source node "done", see registry.py's own
    # docstring), and its "file" output IS just the literal path in its own params. Handle it
    # before the artifact_dir/OUTPUT_FILENAME convention below, which only real compute
    # producers follow.
    if producer.type_id == "source.file":
        path = producer.params.get("path")
        if not path:
            raise ValueError(f"{producer_id}: source.file node has no path")
        return Path(str(path))
    h = hashes.get(producer_id)
    if h is None:
        raise UnresolvedUpstream(producer_id)
    directory = artifact_dir(project_root, producer.type_id, h)
    if producer.type_id in DIR_OUTPUTS:
        return directory
    filename = OUTPUT_FILENAME.get(producer.type_id)
    if filename is None:
        raise ValueError(f"cmd_for: no known output filename for node type {producer.type_id!r}")
    return directory / filename


def _single_upstream_path(
    workflow: Workflow, registry: NodeRegistry, hashes: dict, project_root, node_id: str, input_name: str,
) -> Optional[Path]:
    edges = workflow.edges_into(node_id, input_name)
    if not edges:
        return None
    return _producer_path(workflow, registry, hashes, project_root, edges[0].from_node)


def _approve_target(workflow: Workflow, hashes: dict, node_id: str) -> tuple[str, str]:
    """The downstream `human.approve` node `node_id`'s output eventually reaches, and that
    approve node's own (already-resolved) `input_hash` -- what a human's approval will
    actually be recorded against. Walks forward through the graph (BFS over `edges_from`,
    any number of hops -- `provided.clip` in the overlay recipe reaches its approve node
    through `overlay.place`/`asset.verify`, not directly, and T30b's `behind` branch adds
    `overlay.measure`/`overlay.cutout` before that). Raises if no path from `node_id` reaches
    an approve node at all (a recipe template bug, not a runtime condition)."""
    seen: set[str] = set()
    frontier = [node_id]
    while frontier:
        current = frontier.pop(0)
        for e in workflow.edges_from(current):
            to_node = workflow.node(e.to_node)
            if to_node.type_id == "human.approve":
                h = hashes.get(e.to_node)
                if h is None:
                    raise UnresolvedUpstream(e.to_node)
                return e.to_node, h
            if e.to_node not in seen:
                seen.add(e.to_node)
                frontier.append(e.to_node)
    raise ValueError(f"cmd_for: {node_id!r} has no downstream human.approve node")


def _many_upstream_paths(
    workflow: Workflow, registry: NodeRegistry, hashes: dict, project_root, node_id: str, input_name: str,
) -> list[Path]:
    edges = workflow.edges_into(node_id, input_name)
    return [_producer_path(workflow, registry, hashes, project_root, e.from_node) for e in edges]


def resolve_pick_path(
    workflow: Workflow, registry: NodeRegistry, project_root: str | Path, pick_node_id: str,
) -> Optional[Path]:
    """The artifact path a `human.pick` node currently resolves to, or `None` if it has no
    pick made yet (or that pick's upstream hash isn't resolvable). Public so callers outside
    this package (T30b: `post_api`'s span-workflow route, wiring a `continuity_of_span_id`
    beat's `SpanSpec.continuity_source_path` from *another* beat's already-picked frame) can
    resolve a cross-workflow file path the same way `cmd_for` itself would, without reaching
    into this module's underscore-prefixed helpers."""
    hashes = compute_hashes(workflow, registry)
    try:
        return _producer_path(workflow, registry, hashes, project_root, pick_node_id)
    except (KeyError, UnresolvedUpstream, ValueError):
        return None


def make_cmd_for(workflow: Workflow, registry: NodeRegistry, project_root: str | Path):
    def _cmd_for(node_id: str) -> list[str]:
        hashes = compute_hashes(workflow, registry)
        node = workflow.node(node_id)
        p = node.params
        root = str(project_root)

        if node.type_id == "brief.write":
            import json as _json

            return build_cmd(
                "brief_write", node_id=node_id, project_root=root, instruction=p["instruction"],
                words_text=p.get("words_text", ""), direction_note=p.get("direction_note", ""),
                writer_context=_json.dumps(p.get("writer_context", {})),
            )

        if node.type_id == "still.generate":
            continuity = _many_upstream_paths(workflow, registry, hashes, project_root, node_id, "continuity")
            return build_cmd(
                "still_generate", node_id=node_id, project_root=root, model=p["model"], aspect=p["aspect"],
                prompt=p["prompt_text"], continuity=[str(c) for c in continuity],
                seed=p.get("variant_index", 0), variant_index=p.get("variant_index", 0),
            )

        if node.type_id == "motion.from_frame":
            frame = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "frame")
            return build_cmd(
                "motion_from_frame", node_id=node_id, project_root=root, kit_dir=p["kit_dir"],
                look_path=p.get("look_path"), frame=str(frame),
                subject_motion_hint=p["subject_motion_hint"], static_hint=p["static_hint"],
                camera=p.get("camera"), pacing=p.get("pacing"),
            )

        if node.type_id == "endframe.generate":
            frame = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "frame")
            return build_cmd(
                "endframe_generate", node_id=node_id, project_root=root, model=p["model"], aspect=p["aspect"],
                prompt=p["prompt_text"], frame=str(frame),
            )

        if node.type_id == "video.generate":
            start = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "start_image")
            end = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "end_image")
            motion_path = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "motion_prompt")
            motion_text = Path(motion_path).read_text(encoding="utf-8") if motion_path else ""
            return build_cmd(
                "video_generate", node_id=node_id, project_root=root, model=p["model"], aspect=p["aspect"],
                mode=p["mode"], sound=p.get("sound", True), duration=p["duration"],
                motion_prompt=motion_text, start_image=str(start), end_image=str(end) if end else None,
                crop_to=p.get("crop_to"), fps=p.get("fps"),
            )

        if node.type_id == "animation.design":
            import json as _json

            return build_cmd(
                "animation_design", node_id=node_id, project_root=root, kit_dir=p["kit_dir"],
                look_path=p.get("look_path"), brief_extra=_json.dumps(p.get("brief_extra", {})),
            )

        if node.type_id in ("animation.draft_render", "animation.render"):
            comp_dir = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "composition")
            module = "animation_draft_render" if node.type_id == "animation.draft_render" else "animation_render"
            return build_cmd(
                module, node_id=node_id, project_root=root, composition_dir=str(comp_dir),
                width=p.get("width", 1920), height=p.get("height", 1080), fps=p.get("fps", 30),
            )

        if node.type_id == "overlay.measure":
            video = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "video")
            return build_cmd("overlay_measure", node_id=node_id, project_root=root, video=str(video))

        if node.type_id == "overlay.cutout":
            video = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "video")
            return build_cmd("overlay_cutout", node_id=node_id, project_root=root, video=str(video))

        if node.type_id == "overlay.place":
            video = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "video")
            return build_cmd(
                "overlay_place", node_id=node_id, project_root=root, video=str(video),
                depth=p["depth"], position=p["position"],
            )

        if node.type_id == "aroll.regenerate":
            return build_cmd(
                "aroll_regenerate", node_id=node_id, project_root=root, mode=p["mode"],
                instruction=p.get("instruction", ""),
            )

        if node.type_id == "provided.clip":
            approve_id, approve_hash = _approve_target(workflow, hashes, node_id)
            return build_cmd(
                "provided_clip", node_id=node_id, project_root=root, path=p["path"],
                in_seconds=p.get("in_seconds", 0.0), out_seconds=p.get("out_seconds"),
                record_as_node=approve_id, record_as_hash=approve_hash, role=p.get("role", "picture"),
            )

        if node.type_id == "asset.verify":
            media = _single_upstream_path(workflow, registry, hashes, project_root, node_id, "media")
            approve_id, approve_hash = _approve_target(workflow, hashes, node_id)
            return build_cmd(
                "asset_verify", node_id=node_id, project_root=root, media=str(media),
                expect_kind=p.get("expect_kind", "video"), min_width=p.get("min_width", 0),
                min_height=p.get("min_height", 0), record_as_node=approve_id,
                record_as_hash=approve_hash, role=p.get("role", "picture"),
                expect_fps=p.get("expect_fps"), min_seconds=p.get("min_seconds"),
                expect_aspect=p.get("expect_aspect"), reject_frozen_tail=not p.get("allow_hold", True),
            )

        raise ValueError(f"cmd_for: no argv builder for node type {node.type_id!r}")

    return _cmd_for


__all__ = ["make_cmd_for", "resolve_pick_path", "OUTPUT_FILENAME", "UnresolvedUpstream"]
