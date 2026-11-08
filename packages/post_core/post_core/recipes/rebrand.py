"""T33: re-point an already-built workflow at another brand kit (`post_core.brand.set_project_kit`).

Everything a recipe took from the kit at instantiate time lives on the workflow or in node
params, so switching kits rewrites exactly those. Each rewrite changes the `input_hash` of
the branded nodes (and so of everything downstream): their old outputs stay listed as
stale, and nothing is enqueued here -- regenerating is the editor's call.

- `Workflow.brand_kit_hash` -> the new kit's hash (hashed into every `uses_brand_kit` node).
- `kit_dir` params (`motion.from_frame`, `animation.design`) -> the new kit's folder, so a
  rerun loads the new kit, not the old one.
- `still.generate`/`endframe.generate` `prompt_text`: its `Style: ...` line is the kit's
  text in it (a Brand System kit's accents are always pending), swapped for the new kit's
  style block; a hand-written prompt with no such line has nothing to swap. When the new
  kit cannot brand a prompt (style block pending, or the swapped text fails its purity
  check) the node keeps its text and is reported as `unbranded`.
- `brief.write`'s `writer_context` -> the new kit's.
"""
from __future__ import annotations

import hashlib

from brandkit.compile import find_prompt_violations, writer_context
from brandkit.schema import BrandKit

from ..graph.workflow import Node, Workflow

STYLE_PREFIX = "Style: "
PROMPT_NODE_TYPES = ("still.generate", "endframe.generate")


def _style_hash(text: str) -> str:
    # Same 12-char sha256 `brandkit.compile.still_prompt` records as `style_block_hash`.
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _has_style_line(prompt: str) -> bool:
    return any(line.startswith(STYLE_PREFIX) for line in prompt.split("\n"))


def _restyle(prompt: str, style: str) -> str:
    return "\n".join(f"{STYLE_PREFIX}{style}" if line.startswith(STYLE_PREFIX) else line for line in prompt.split("\n"))


def _rebrand_node(node: Node, kit: BrandKit, style: str | None, context: dict) -> tuple[Node, bool]:
    """(the node with its kit-derived params rewritten, whether it is left unbranded)."""
    params = dict(node.params)
    unbranded = False
    if "kit_dir" in params:
        params["kit_dir"] = str(kit.path)
    if "writer_context" in params:
        params["writer_context"] = context
    if node.type_id in PROMPT_NODE_TYPES and _has_style_line(str(params.get("prompt_text") or "")):
        restyled = _restyle(params["prompt_text"], style) if style else None
        if restyled is None or find_prompt_violations(restyled, kit):
            unbranded = True
        else:
            params["prompt_text"] = restyled
            if node.type_id == "still.generate":
                params["style_block_version"] = kit.stills_style_block.version
                params["style_block_hash"] = _style_hash(style)
    if params == node.params:
        return node, unbranded
    return node.model_copy(update={"params": params}), unbranded


def rebrand_workflow(workflow: Workflow, kit: BrandKit) -> tuple[Workflow, list[str]]:
    """Return (`workflow` re-pointed at `kit`, ids of prompt nodes the kit could not brand).
    Pure: the caller persists the result. Unchanged when `workflow` already uses `kit`."""
    sb = kit.stills_style_block
    style = sb.text if sb.status == "filled" and sb.text else None
    context = writer_context(kit)
    nodes: list[Node] = []
    unbranded: list[str] = []
    for node in workflow.nodes:
        new_node, left = _rebrand_node(node, kit, style, context)
        nodes.append(new_node)
        if left:
            unbranded.append(node.id)
    updated = workflow.model_copy(update={"nodes": nodes, "brand_kit_hash": kit.kit_hash()})
    return updated, unbranded


__all__ = ["rebrand_workflow"]
