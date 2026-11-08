"""The `TextProvider`/terminal-agent pattern (same shape as `brandkit.generate.TextProvider`)
for T13b/T30b's "Suggest visuals" pass.

`AgentSuggestProvider` is the real-mode provider (T36): it renders `suggest_prompt.
build_suggest_prompt` and asks the operation's terminal agent (`post_core.agents`, Claude or
Codex CLI on the subscription, read-only) for `{"proposals": [...]}`. `FakeTextProvider` is
a canned-response double for tests. `DeterministicSuggester` is the `POST3_FAKE_PROVIDERS=1`
demo path: it makes NO agent call at all -- one proposal per long sentence that contains a
concrete noun, capped, cycling deterministically through every T30 medium and both overlay
depths across a long transcript -- so the demo shows real-looking, taxonomy-complete
proposals without needing a live model.
"""
from __future__ import annotations

import json
import re
from typing import Protocol

from ..model.cut import valid_overlay_positions

_STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "into", "your", "their", "have", "will",
    "just", "about", "when", "then", "than", "were", "been", "being", "what", "which",
    "there", "here", "some", "every", "each", "over", "under", "them", "they", "these",
    "those", "would", "could", "should", "because", "while", "before", "after",
}


class SuggestProvider(Protocol):
    def draft(self, context: dict) -> str:
        """Return raw text (expected to contain a JSON array) proposing visual beats from
        `context`: the brand `writer_context`, `cast`, `scope`, `sentences` (the scope's
        words), `sections` (the cut's words by section) and `neighbours` (sequence context)
        -- see `suggest.generate_suggestions`."""
        ...


class SuggestProviderError(ValueError):
    """`suggest_visuals` (or a provider it called) failed."""


class AgentSuggestProvider:
    """Real mode: one terminal-agent call per run (`operation="suggest_visuals"`, provider and
    model from the project's `.post3/agents.json`). `ask` is injectable for tests; it
    defaults to `post_core.agents.ask_json`. Agent failures (including a reply with no
    `proposals` list) surface as `post_core.agents.AgentError`s."""

    def __init__(self, project_root=None, ask=None):
        self.project_root = project_root
        self._ask = ask

    def draft(self, context: dict) -> str:
        from ..agents import AgentBadJSON, ask_json
        from .suggest_prompt import build_suggest_prompt, proposals_from_reply

        prompt = build_suggest_prompt(context)
        ask = self._ask or ask_json
        reply = ask(prompt.text, "suggest_visuals", project_root=self.project_root)
        try:
            proposals = proposals_from_reply(reply, prompt.aliases)
        except ValueError as exc:
            raise AgentBadJSON(f"suggest_visuals: {exc}; nothing was applied") from exc
        return json.dumps(proposals)


class FakeTextProvider:
    """Test double: returns a canned response and records every call it received."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict] = []

    def draft(self, context: dict) -> str:
        self.calls.append(context)
        return self.response


def parse_suggest_response(raw: str) -> list[dict]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        raise SuggestProviderError("suggest provider response did not contain a JSON array")
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise SuggestProviderError(f"suggest provider response was not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise SuggestProviderError("suggest provider response JSON was not a list")
    return [p for p in parsed if isinstance(p, dict)]


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_MEDIUM_CYCLE = ("live_action", "motion_graphic", "provided", "aroll")


def _concrete_noun(words: list[dict]) -> str | None:
    """Cheapest possible heuristic for "a concrete noun worth showing": the longest
    alphabetic word (not the sentence's first word, not a stopword)."""
    candidates = [
        w["text"] for i, w in enumerate(words)
        if i > 0 and _WORD_RE.fullmatch(w["text"]) and w["text"].lower() not in _STOPWORDS and len(w["text"]) >= 5
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


class DeterministicSuggester:
    """The `POST3_FAKE_PROVIDERS=1` demo suggester: no provider call, no randomness -- one
    proposal per long sentence with a concrete noun, capped, cycling through every T30
    medium (`_MEDIUM_CYCLE`) and, on every other beat, an overlay alternating depth (`behind`
    only when that beat's medium is `aroll` -- the only medium it's ever legal over)."""

    def __init__(self, cap: int = 8, min_words: int = 9):
        self.cap = cap
        self.min_words = min_words

    def draft(self, context: dict) -> str:
        proposals: list[dict] = []
        i = 0
        audio_only = context.get("picture_mode") == "audio_only"  # T42: no presenter, so no aroll
        cycle = tuple(m for m in _MEDIUM_CYCLE if not (audio_only and m == "aroll"))
        for sentence in context.get("sentences", []):
            if len(proposals) >= self.cap:
                break
            words = sentence["words"]
            if len(words) < self.min_words:
                continue
            noun = _concrete_noun(words)
            if noun is None:
                continue
            medium = cycle[i % len(cycle)]
            proposal: dict = {
                "start_word_id": words[0]["id"], "end_word_id": words[-1]["id"],
                "medium": medium, "brief": f"Show {noun}.",
                "rationale": f"Long sentence naming '{noun}' -- a concrete beat worth a visual.",
            }
            if i % 2 == 1:
                depth = "behind" if medium == "aroll" else "in_front"
                positions = sorted(valid_overlay_positions(medium, depth))
                if positions:
                    proposal["overlay"] = {"depth": depth, "position": positions[0]}
            if any(w["text"].isdigit() for w in words):
                proposal["flags"] = ["must_have_shot"]
            proposals.append(proposal)
            i += 1
        return json.dumps(proposals)


__all__ = [
    "SuggestProvider", "SuggestProviderError", "AgentSuggestProvider", "FakeTextProvider",
    "DeterministicSuggester", "parse_suggest_response",
]
