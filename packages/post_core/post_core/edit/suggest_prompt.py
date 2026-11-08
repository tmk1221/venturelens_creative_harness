"""T36: the Suggest-visuals prompt a terminal agent answers -- brand writer context (the
project's kit, T33), the picture mode (T42), the T30 beat taxonomy, the cut's transcript by
section and the neighbouring beats. T42: no editorial rules; the rationale is a plain-language
"why this picture fits these words". In `audio_only` mode the prompt asks for full coverage
and offers no aroll/behind -- `suggest_coverage` enforces it whatever the agent replies.

Words are shown as `[n]word` with short numbers instead of their 32-character ids: cheaper to
send, and nothing for the agent to mistype. `build_suggest_prompt` returns the prompt plus
the number -> word-id map; `proposals_from_reply` maps the agent's `start`/`end` numbers back
to word ids (an unknown number becomes an id no transcript has, so validation drops it).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

MEDIA = {
    "aroll": "  aroll: keep the presenter on camera, nothing generated -- the words and the face carry it.",
    "provided": "  provided: the editor's own footage (a clip + in/out) -- when a real shot of the thing being\n"
                "    discussed plausibly already exists in the project's footage.",
    "live_action": "  live_action: generated video (stills -> pick -> motion -> video) -- a concrete visual beat\n"
                   "    with nothing suitable on hand.",
    "motion_graphic": "  motion_graphic: a full-frame generated animation -- data, a process, a title card, or an\n"
                      "    abstract idea that a diagram, chart or kinetic type can show.",
}

OVERLAY_PRESENTER = """
OVERLAY (optional, independent of picture; only when it earns its place):
  depth: in_front (over the picture) or behind (the presenter is cut out and the overlay sits
    behind them -- only over aroll).
  position, given depth and picture medium:
    aroll + in_front: right | left | lower-band
    aroll + behind: right | left | full-frame
    any other medium + in_front: right | left | lower-band | center | full-width
    any other medium + behind: never.
""".strip()

OVERLAY_AUDIO_ONLY = """
OVERLAY (optional, on top of the beat's picture; only when it earns its place):
  depth: in_front only (there is no presenter to cut out, so never behind).
  position: right | left | lower-band | center | full-width
""".strip()

PICTURE_MODE_TEXT = {
    "presenter": "PICTURE MODE: presenter on camera. Wherever no beat changes the picture, the presenter "
                 "stays in frame, so only propose a picture where it adds something.",
    "audio_only": "PICTURE MODE: audio only. There is no presenter picture: the soundtrack is a voice, and "
                  "every second of the cut needs a picture. Propose picture beats that cover every word of "
                  "the transcript, back to back, with no gaps and no overlaps. Never use medium aroll and "
                  "never use a behind overlay.",
}


def taxonomy(picture_mode: str = "presenter") -> str:
    audio_only = picture_mode == "audio_only"
    media = [k for k in MEDIA if not (audio_only and k == "aroll")]
    if audio_only:
        flags = ("FLAGS (any subset): must_have_shot (non-negotiable in the cut), picture_must_match_words "
                 "(the picture must literally show what is said).")
    else:
        flags = ("FLAGS (any subset): must_have_shot (non-negotiable in the cut), presenter_stays_on_camera\n"
                 "(don't cut away here), picture_must_match_words (the picture must literally show what is said).")
    head = "PICTURE MEDIUM (exactly one per beat)" if audio_only else \
        "PICTURE MEDIUM (exactly one per beat, or none for an overlay-only beat)"
    return "\n\n".join([
        "BEAT MODEL -- choose the whole beat, not just \"a visual\":",
        head + ":\n" + "\n".join(MEDIA[k] for k in media),
        OVERLAY_AUDIO_ONLY if audio_only else OVERLAY_PRESENTER,
        flags,
    ])


TAXONOMY = taxonomy("presenter")


def reply_format(picture_mode: str = "presenter") -> str:
    audio_only = picture_mode == "audio_only"
    media = " | ".join(f'"{k}"' for k in MEDIA if not (audio_only and k == "aroll"))
    medium_line = f'  "medium": {media},' if audio_only else f'  "medium": {media} (omit for overlay-only),'
    tail = ("Cover every word: one proposal per stretch of words, back to back."
            if audio_only else "Only propose beats that add something concrete; an empty list is a valid answer.")
    return "\n".join([
        "Return only this JSON object, no prose:",
        '{"proposals": [{"start": <word number>, "end": <word number>,',
        medium_line,
        '  "overlay": {"depth": ..., "position": ...} (omit when there is no overlay),',
        '  "flags": [...], "cast_refs": [names from the recurring cast, if any],',
        '  "brief": "one line: what the viewer sees",',
        '  "direction_note": "one line: editor-style direction",',
        '  "rationale": "one line, plain language: why this picture fits these words"}]}',
        "To offer a second idea for the same words, add another proposal with the same start and end.",
        tail,
    ])


REPLY_FORMAT = reply_format("presenter")


@dataclass
class SuggestPrompt:
    text: str
    aliases: dict[int, str] = field(default_factory=dict)


def _brand_lines(context: dict) -> list[str]:
    labels = (("identity", "Identity"), ("personality", "Personality"), ("world", "World"),
              ("accents", "Accents"), ("camera_personality", "Camera personality"))
    lines = [f"{label}: {context[key]}" for key, label in labels if context.get(key)]
    lines.append(f"Recurring cast this project can reference: {json.dumps(context.get('cast', []))}")
    return lines


def _transcript_lines(context: dict, aliases: dict[int, str], number_of: dict[str, int]) -> list[str]:
    sections = context.get("sections") or [{"title": "", "sentences": context.get("sentences", [])}]
    lines: list[str] = []
    for section in sections:
        lines.append(f"## Section: {section.get('title') or '(untitled)'}")
        for sentence in section.get("sentences", []):
            parts = []
            for word in sentence["words"]:
                n = len(aliases) + 1
                aliases[n] = word["id"]
                number_of[word["id"]] = n
                parts.append(f"[{n}]{word['text']}")
            who = sentence.get("speaker") or "speaker"
            seconds = sentence.get("seconds")
            head = f"({who}, {seconds:g} s)" if isinstance(seconds, (int, float)) else f"({who})"
            lines.append(f"{head} {' '.join(parts)}")
    return lines


def _beat_lines(context: dict, number_of: dict[str, int]) -> list[str]:
    lines = []
    for beat in context.get("neighbours", []):
        s, e = number_of.get(beat["start_word_id"]), number_of.get(beat["end_word_id"])
        where = f"[{s}]-[{e}]" if s and e else f"{beat['where']} the scope"
        picture = beat.get("medium") or "no picture change"
        overlay = beat.get("overlay")
        if overlay:
            picture += f" + overlay {overlay['depth']}/{overlay['position']}"
        state = "pending proposal" if beat.get("status") == "proposed" else f"placed by {beat.get('placed_by', 'human')}"
        lines.append(f"- {where} \"{beat['words']}\": {picture}; brief: {beat.get('brief') or '(none)'} ({state})")
    return lines or ["(none yet)"]


def build_suggest_prompt(context: dict) -> SuggestPrompt:
    """The full prompt for one Suggest-visuals run over `context` (built by
    `suggest.generate_suggestions`)."""
    aliases: dict[int, str] = {}
    number_of: dict[str, int] = {}
    transcript = _transcript_lines(context, aliases, number_of)
    scope = "a selection of the cut" if context.get("scope") == "selection" else "the whole cut"
    mode = "audio_only" if context.get("picture_mode") == "audio_only" else "presenter"
    text = "\n\n".join([
        "You are the B-roll editor for a short branded video. Propose what the viewer should SEE "
        f"at specific moments of {scope}. Each proposal is only a suggestion: the editor accepts "
        "or dismisses it, and it never replaces anything already placed.",
        "BRAND (writer context from the project's brand kit):\n" + "\n".join(_brand_lines(context)),
        PICTURE_MODE_TEXT[mode],
        taxonomy(mode),
        "TRANSCRIPT OF THE CUT, BY SECTION -- each line is one sentence with its speaker and spoken "
        "length; each word is shown as [n]word, and you refer to words by n:\n" + "\n".join(transcript),
        "NEIGHBOURING BEATS (sequence context, in order; placed beats are the editor's and stay as they "
        "are):\n" + "\n".join(_beat_lines(context, number_of)),
        reply_format(mode),
    ])
    return SuggestPrompt(text=text + "\n", aliases=aliases)


def _word_id(value, aliases: dict[int, str]) -> str:
    try:
        return aliases[int(value)]
    except (KeyError, TypeError, ValueError):
        return f"unknown-word-{value}"


def proposals_from_reply(reply: dict, aliases: dict[int, str]) -> list[dict]:
    """The reply's proposals with `start`/`end` numbers turned into `start_word_id`/
    `end_word_id`. Raises `ValueError` if `proposals` is not a list."""
    proposals = reply.get("proposals")
    if not isinstance(proposals, list):
        raise ValueError("the agent's reply has no 'proposals' list")
    out = []
    for raw in proposals:
        if not isinstance(raw, dict):
            continue
        item = {k: v for k, v in raw.items() if k not in ("start", "end")}
        item["start_word_id"] = _word_id(raw.get("start"), aliases)
        item["end_word_id"] = _word_id(raw.get("end"), aliases)
        out.append(item)
    return out


__all__ = ["TAXONOMY", "REPLY_FORMAT", "PICTURE_MODE_TEXT", "taxonomy", "reply_format", "SuggestPrompt", "build_suggest_prompt", "proposals_from_reply"]
