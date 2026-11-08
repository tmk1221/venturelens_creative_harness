"""`brief.write`: an agent job that writes a short brief from an instruction (T12 spec).

Fake mode (`POST3_FAKE_PROVIDERS=1`) writes a deterministic placeholder brief -- no agent
call, nothing paid or networked. Real mode (T36) asks the project's terminal agent for
`brief_write` (`post_core.agents.ask_json`: Claude or Codex CLI on the subscription,
read-only, provider/model from `.post3/agents.json`) with the beat's words, the editor's
direction and the brand writer context; the node's `writer_context` param is the project's
kit (set at instantiate time, kept current by `recipes.rebrand`), and an empty one falls back
to the project's kit here. The brief is written only after the reply validates; any agent
failure exits 1 with the reason and writes nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ...agents import AgentError, ask_json
from ...workers.contract import emit
from ..agent_prompts import brief_from_reply, brief_prompt
from ._common import add_common_args, emit_artifact_ok, fake_mode


def _fake_brief(instruction: str, words_text: str, direction_note: str, writer_context: dict) -> str:
    """T30b: a plausible-looking brief composed from the beat's words + editor direction +
    the brand's writer_context (identity/personality/world) -- no agent call, deterministic.
    Falls back to the plain T12 echo (`instruction` alone) when none of the extra context was
    given, so `_build_motion_graphic`'s existing callers keep their exact old output."""
    if not (words_text or direction_note or writer_context):
        return instruction
    parts = []
    if direction_note:
        parts.append(direction_note.strip())
    elif instruction:
        parts.append(instruction.strip())
    if words_text:
        snippet = " ".join(words_text.split()[:24])
        parts.append(f"over: \"{snippet}\"")
    identity = writer_context.get("identity") if isinstance(writer_context, dict) else None
    if identity:
        parts.append(f"in brand voice: {identity}")
    return " -- ".join(p for p in parts if p) or instruction


def _agent_brief(args: argparse.Namespace, writer_context: dict) -> str:
    if not writer_context:
        from ...brand import project_writer_context

        writer_context = project_writer_context(args.project_root)
    prompt = brief_prompt(args.instruction, args.words_text, args.direction_note, writer_context)
    reply = ask_json(
        prompt, "brief_write", project_root=args.project_root,
        on_prompt=lambda text, choice: emit("prompt", text=text, model=choice.label, provider=choice.provider),
    )
    return brief_from_reply(reply)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--words-text", default="")
    parser.add_argument("--direction-note", default="")
    parser.add_argument("--writer-context", default="{}")
    parser.add_argument("--out", default="brief.txt")
    args = parser.parse_args(argv)

    try:
        writer_context = json.loads(args.writer_context)
    except ValueError:
        writer_context = {}
    if not isinstance(writer_context, dict):
        writer_context = {}

    out_path = Path(args.out)
    if fake_mode():
        text = _fake_brief(args.instruction, args.words_text, args.direction_note, writer_context)
    else:
        try:
            text = _agent_brief(args, writer_context)
        except AgentError as exc:
            emit("result", ok=False, detail=f"brief.write: {exc}", reason=exc.reason)
            return 1
    out_path.write_text(text, encoding="utf-8")
    emit_artifact_ok(out_path, role="text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
