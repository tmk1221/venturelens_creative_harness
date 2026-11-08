"""T42: what happens to a Suggest reply after each proposal is validated on its own --

- `merge_same_range`: two ideas for the same words become one proposal with variants (A, B, ...)
  the person switches between on the card, so there is one proposal per passage.
- `tile_audio_only`: in `audio_only` picture mode, full coverage is a guarantee, not a hint.
  Every word of the scope that no placed (or kept pending) picture beat already covers ends up
  under exactly one proposed picture beat: contiguous, no gaps, no overlaps, never `aroll`.
  Overlaps are trimmed (a proposal inside another becomes its variant), gaps go to the nearest
  beat word by word, and a stretch the agent left empty gets one plain filler beat.

Positions are word indices in the scope's sync group (`TranscriptIndex.index_of`); `word_ids`
is that sync group's word ids in order, to turn indices back into anchors.
"""
from __future__ import annotations

from typing import Optional

from ..model.base import new_id
from ..model.common import WordAnchor
from .suggest_models import Suggestion, layers_for

Placed = tuple[int, int, Suggestion]

FILLER_RATIONALE = "Audio only: nothing was proposed for these words, and every second needs a picture."
SNIPPET_WORDS = 8


def add_variant(primary: Suggestion, other: Suggestion) -> Suggestion:
    """`primary` with `other`'s idea as one more variant (an identical idea adds nothing)."""
    active = primary.active_variant if primary.variants else 0
    ideas = list(primary.variants) or [primary.idea()]
    ideas[active] = primary.idea()
    for idea in other.variants or [other.idea()]:
        if idea not in ideas:
            ideas.append(idea)
    if len(ideas) == 1:
        return primary
    return primary.model_copy(update={"variants": ideas, "active_variant": active})


def merge_same_range(items: list[Placed]) -> list[Placed]:
    """Proposals on identical word ranges and a shared layer (two pictures, say -- a picture and
    an overlay-only beat go together, they are not alternatives) folded into the first one's
    variants, order kept."""
    out: list[Placed] = []
    for s, e, suggestion in items:
        layers = set(layers_for(suggestion))
        i = next((i for i, (os_, oe, other) in enumerate(out)
                  if (os_, oe) == (s, e) and layers & set(layers_for(other))), None)
        if i is None:
            out.append((s, e, suggestion))
        else:
            out[i] = (s, e, add_variant(out[i][2], suggestion))
    return out


def free_stretches(start_i: int, end_i: int, blocked: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """`[start_i, end_i]` minus every blocked range, as inclusive stretches in order."""
    stretches: list[tuple[int, int]] = []
    cursor = start_i
    for s, e in sorted(blocked):
        if e < cursor or s > end_i:
            continue
        if s > cursor:
            stretches.append((cursor, s - 1))
        cursor = max(cursor, e + 1)
    if cursor <= end_i:
        stretches.append((cursor, end_i))
    return stretches


def _retarget(suggestion: Suggestion, s: int, e: int, word_ids: list[str], fresh_id: bool) -> Suggestion:
    transcript_id = suggestion.start_anchor.transcript_id
    update = {
        "start_anchor": WordAnchor(transcript_id=transcript_id, word_id=word_ids[s]),
        "end_anchor": WordAnchor(transcript_id=transcript_id, word_id=word_ids[e]),
    }
    if fresh_id:
        update["id"] = new_id()
    return suggestion.model_copy(update=update)


def _filler(transcript_id: str, s: int, e: int, word_ids: list[str], words_text: list[str]) -> Suggestion:
    snippet = " ".join(words_text[s : min(e + 1, s + SNIPPET_WORDS)])
    snippet += " ..." if e + 1 - s > SNIPPET_WORDS else ""
    return Suggestion(
        start_anchor=WordAnchor(transcript_id=transcript_id, word_id=word_ids[s]),
        end_anchor=WordAnchor(transcript_id=transcript_id, word_id=word_ids[e]),
        medium="live_action", brief=f"A picture for: {snippet}", rationale=FILLER_RATIONALE,
    )


def _tile_stretch(a: int, b: int, items: list[Placed]) -> list[list]:
    """Proposals clipped to `[a, b]` and made an exact tiling of it (mutable `[s, e, suggestion]`)."""
    clipped = sorted(([max(s, a), min(e, b), sg] for s, e, sg in items if s <= b and e >= a),
                     key=lambda it: (it[0], -it[1]))
    tiles: list[list] = []
    for it in clipped:
        if tiles and it[0] <= tiles[-1][1]:
            if it[1] <= tiles[-1][1]:  # inside the previous beat: its idea becomes a variant
                tiles[-1][2] = add_variant(tiles[-1][2], it[2])
                continue
            it[0] = tiles[-1][1] + 1  # overlaps the previous beat's end: trim its start
        tiles.append(it)
    if not tiles:
        return tiles
    tiles[0][0], tiles[-1][1] = a, b
    for prev, nxt in zip(tiles, tiles[1:]):
        gap = nxt[0] - prev[1] - 1
        if gap > 0:  # each word goes to the nearer beat; a tie goes to the earlier one
            prev[1] += (gap + 1) // 2
            nxt[0] = prev[1] + 1
    return tiles


def tile_audio_only(
    items: list[Placed], start_i: int, end_i: int, blocked: list[tuple[int, int]],
    word_ids: list[str], words_text: list[str], transcript_id: str,
) -> list[Placed]:
    """Picture proposals (already without `aroll`) turned into an exact tiling of every word in
    `[start_i, end_i]` not covered by `blocked`. A proposal crossing a blocked range is split
    into one piece per side (the extra pieces get new ids)."""
    out: list[Placed] = []
    used: set[str] = set()
    for a, b in free_stretches(start_i, end_i, blocked):
        tiles = _tile_stretch(a, b, items)
        if not tiles:
            out.append((a, b, _filler(transcript_id, a, b, word_ids, words_text)))
            continue
        for s, e, suggestion in tiles:
            fresh = suggestion.id in used
            used.add(suggestion.id)
            out.append((s, e, _retarget(suggestion, s, e, word_ids, fresh)))
    return out


def is_exact_tiling(ranges: list[tuple[int, int]], start_i: int, end_i: int,
                    blocked: Optional[list[tuple[int, int]]] = None) -> bool:
    """True when `ranges` plus `blocked` cover `[start_i, end_i]` once each, nothing outside."""
    covered = [0] * (end_i - start_i + 1)
    for s, e in [*ranges, *(blocked or [])]:
        for i in range(max(s, start_i), min(e, end_i) + 1):
            covered[i - start_i] += 1
    return all(c == 1 for c in covered) and all(start_i <= s <= e <= end_i for s, e in ranges)


__all__ = ["add_variant", "merge_same_range", "free_stretches", "tile_audio_only", "is_exact_tiling",
           "FILLER_RATIONALE"]
