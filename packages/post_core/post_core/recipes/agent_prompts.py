"""T36: the prompts `brief.write` and `motion.from_frame` send to a terminal agent in real mode,
and the checks on what comes back. Kept apart from the workers so a prompt can be read and
tested without running a subprocess.

Both prompts carry the project kit's writer context (`brandkit.compile.writer_context`: the
node's own `writer_context` param for briefs, the node's kit for motion) and ask for one JSON
object. Neither reply is trusted as-is: the brief must be non-empty text, and the motion
slots go through `brandkit.compile.motion_prompt`'s purity check before anything is written.
"""
from __future__ import annotations

from typing import Iterable, Optional

from ..agents import AgentBadJSON


def _brand_block(writer_context: dict) -> str:
    labels = (("identity", "Identity"), ("personality", "Personality"), ("world", "World"),
              ("accents", "Accents"), ("camera_personality", "Camera personality"))
    lines = [f"{label}: {writer_context[key]}" for key, label in labels if writer_context.get(key)]
    return "\n".join(lines) or "(no brand context filled in yet)"


def brief_prompt(instruction: str, words_text: str, direction_note: str, writer_context: dict) -> str:
    return "\n\n".join([
        "You write the brief for one beat of a branded video: what the viewer sees while these "
        "words are spoken. An animator builds a full-frame motion graphic from your brief.",
        "BRAND (writer context from the project's brand kit):\n" + _brand_block(writer_context),
        f"WORDS SPOKEN OVER THIS BEAT:\n{words_text.strip() or '(none given)'}",
        f"EDITOR'S DIRECTION:\n{direction_note.strip() or '(none given)'}",
        f"INSTRUCTION:\n{instruction.strip() or '(none given)'}",
        "RULES:\n"
        "- Two to four plain sentences: the one idea the picture shows, what is on screen, and how "
        "it builds or moves over the length of the words.\n"
        "- Show what the words cannot: a process, a number, a comparison, a new term.\n"
        "- Say what is on screen, not what to avoid. No hex colour codes, font names or logo "
        "placement -- the brand kit supplies those.\n"
        "- Match the brand's personality; follow the editor's direction where it is given.",
        'Return only this JSON object: {"brief": "<the brief>"}',
    ]) + "\n"


def brief_from_reply(reply: dict) -> str:
    brief = reply.get("brief")
    if not isinstance(brief, str) or not brief.strip():
        raise AgentBadJSON("brief.write: the agent's reply has no non-empty 'brief'; nothing was written")
    return brief.strip()


def motion_prompt_request(
    subject_motion_hint: str, static_hint: str, camera: Optional[str], pacing: Optional[str],
    writer_context: dict, forbidden: Iterable[str],
) -> str:
    camera_line = camera or (f"the brand default ({writer_context['camera_personality']})"
                             if writer_context.get("camera_personality") else "the house default")
    avoid = ", ".join(forbidden) or "(none)"
    return "\n\n".join([
        "You write the motion half of an image-to-video prompt. The attached image is the picked "
        "start frame of a B-roll shot; a video model will animate exactly this frame. Look at it "
        "and describe only what moves and what holds still.",
        "BRAND (writer context from the project's brand kit):\n" + _brand_block(writer_context),
        "THE EDITOR'S INTENT FOR THIS BEAT:\n"
        f"- Subject motion (hint): {subject_motion_hint.strip() or '(none given)'}\n"
        f"- Static (hint): {static_hint.strip() or '(none given)'}\n"
        f"- Camera (already decided; do not describe camera moves): {camera_line}\n"
        f"- Pacing (already decided): {pacing or 'the brand default'}",
        "RULES:\n"
        "- Motion must be plausible from this exact frame: things visible in it, moving the way "
        "the frame allows. One continuous action over a few seconds; no cuts, no new scene.\n"
        "- Never restate style, lighting, colour or palette -- the frame already carries them.\n"
        "- No brand or product names, logos, on-screen text, quotation marks or hex colours.\n"
        "- Say what happens, not what must not happen.\n"
        f"- Never use these motion terms: {avoid}.",
        'Return only this JSON object: {"subject_motion": "<one sentence>", "static": "<what holds still>"}',
    ]) + "\n"


def motion_slots_from_reply(reply: dict) -> tuple[str, str]:
    subject, static = reply.get("subject_motion"), reply.get("static")
    if not (isinstance(subject, str) and subject.strip() and isinstance(static, str) and static.strip()):
        raise AgentBadJSON("motion.from_frame: the agent's reply needs non-empty 'subject_motion' and 'static'")
    return subject.strip().rstrip("."), static.strip().rstrip(".")


__all__ = ["brief_prompt", "brief_from_reply", "motion_prompt_request", "motion_slots_from_reply"]
