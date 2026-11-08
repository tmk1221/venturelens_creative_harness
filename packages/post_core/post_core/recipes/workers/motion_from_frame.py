"""`motion.from_frame`: write the motion prompt for a picked start frame (T12 spec: "agent
rewrites motion prompt from the picked frame"), built through `brandkit.compile.motion_prompt`
and gated by the kit's purity check.

Real mode (T36): the project's terminal agent for `motion_from_frame` (`post_core.agents.
ask_json`, Claude or Codex CLI on the subscription, read-only) looks at `--frame` with the
beat's `--subject-motion-hint`/`--static-hint` as the editor's intent and the kit's writer
context, and returns the `subject_motion`/`static` slots. Camera and pacing stay the beat's
own (or the kit's defaults) -- the agent never changes them. Fake mode
(`POST3_FAKE_PROVIDERS=1`) makes no agent call and uses the hints as the slots, exactly as
before T36. Either way the slots go through `build_motion_prompt`, so brand-impure text
(hex codes, quotes, brand words, forbidden motion terms) fails the node instead of reaching a
paid video generator.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from brandkit.compile import CompileError, writer_context
from brandkit.look import Look
from brandkit.schema import BrandKit

from ...agents import AgentError, ask_json
from ...workers.contract import emit
from ..agent_prompts import motion_prompt_request, motion_slots_from_reply
from ..prompts import build_motion_prompt
from ._common import add_common_args, fake_mode


def _agent_slots(args: argparse.Namespace, kit: BrandKit, look) -> tuple[str, str]:
    forbidden = kit.house.get("motion_design", {}).get("forbidden", [])
    prompt = motion_prompt_request(
        args.subject_motion_hint, args.static_hint, args.camera, args.pacing, writer_context(kit, look), forbidden,
    )
    reply = ask_json(
        prompt, "motion_from_frame", images=[args.frame], project_root=args.project_root,
        on_prompt=lambda text, choice: emit("prompt", text=text, model=choice.label, provider=choice.provider),
    )
    return motion_slots_from_reply(reply)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--kit-dir", required=True)
    parser.add_argument("--look-path", default=None)
    parser.add_argument("--frame", required=True)
    parser.add_argument("--subject-motion-hint", required=True)
    parser.add_argument("--static-hint", required=True)
    parser.add_argument("--camera", default=None)
    parser.add_argument("--pacing", default=None)
    parser.add_argument("--out", default="motion_prompt.txt")
    args = parser.parse_args(argv)

    kit = BrandKit.load(args.kit_dir)
    look = Look.load(args.look_path) if args.look_path else None
    if fake_mode():
        subject_motion, static = args.subject_motion_hint, args.static_hint
    else:
        try:
            subject_motion, static = _agent_slots(args, kit, look)
        except AgentError as exc:
            emit("result", ok=False, detail=f"motion.from_frame: {exc}", reason=exc.reason)
            return 1
    slots = {"subject_motion": subject_motion, "static": static, "camera": args.camera, "pacing": args.pacing}
    try:
        text = build_motion_prompt(slots, kit, look)
    except CompileError as exc:
        emit("result", ok=False, detail=f"motion.from_frame: {exc}")
        return 1

    out_path = Path(args.out)
    out_path.write_text(text, encoding="utf-8")
    emit("prompt", text=text, model="brandkit.motion_prompt")
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    emit("artifact", path=str(out_path), role="text", sha256=sha, source_frame=args.frame)
    emit("result", ok=True, detail="done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
