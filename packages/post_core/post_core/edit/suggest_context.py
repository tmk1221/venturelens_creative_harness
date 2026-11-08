"""T36: what the Suggest-visuals agent reads besides the brand -- the cut's transcript by
section, and the neighbouring beats (sequence context).

`transcript_by_section`: the cut's own words (its passages, in cut order, clipped to the
scope), grouped under the cut's section titles and split into sentences, each sentence with
its speaker's display name (T35) and its spoken length. Words a passage leaves out are not
sent, so the agent never proposes a visual over something already cut.

`neighbouring_beats`: every beat already in the scope, plus the nearest few just before and
after it, each with its words, picture medium, overlay, brief and whether a human placed it
or it is still a pending proposal. Placed beats are the editor's decisions -- context, never
something to propose over (`suggest.generate_suggestions` drops any same-layer overlap).
"""
from __future__ import annotations

from typing import Iterable, Optional

from ..model.cut import Cut
from ..model.transcript import Word
from .ranges import TranscriptIndex
from .suggest_models import Suggestion

SENTENCE_END = (".", "!", "?")
NEIGHBOURS_PER_SIDE = 3
MAX_BEATS_INSIDE = 80
SNIPPET_WORDS = 20


def split_sentences(words: Iterable[Word], speakers: Optional[dict[str, str]] = None) -> list[dict]:
    """`[{"words": [{"id", "text"}], "speaker", "seconds"}]` -- a new sentence after end-of-
    sentence punctuation or a change of speaker."""
    names = speakers or {}
    sentences: list[dict] = []
    current: list[Word] = []

    def close() -> None:
        if current:
            sentences.append({
                "speaker": names.get(current[0].speaker, current[0].speaker),
                "seconds": round(max(0.0, current[-1].end - current[0].start), 1),
                "words": [{"id": w.id, "text": w.text} for w in current],
            })
            current.clear()

    for word in words:
        if current and word.speaker != current[-1].speaker:
            close()
        current.append(word)
        if word.text.rstrip("'\")").endswith(SENTENCE_END):
            close()
    close()
    return sentences


def transcript_by_section(cut: Cut, index: TranscriptIndex, sync_group_id: str, start_i: int, end_i: int) -> list[dict]:
    """`[{"title", "sentences"}]` for the cut's words inside `[start_i, end_i]`. Falls back to
    the scope's raw word range (one untitled section) when no passage covers it."""
    transcript = index.transcript_for(sync_group_id)
    all_words = index.words(sync_group_id)
    title_of = {pid: section.title for section in cut.sections for pid in section.passage_ids}
    groups: list[tuple[str, list[Word]]] = []
    for passage in cut.passages:
        if passage.sync_group_id != sync_group_id:
            continue
        try:
            lo = max(index.index_of(sync_group_id, passage.start_word_id), start_i)
            hi = min(index.index_of(sync_group_id, passage.end_word_id), end_i)
        except KeyError:
            continue
        if lo > hi:
            continue
        title = title_of.get(passage.id, "")
        if not groups or groups[-1][0] != title:
            groups.append((title, []))
        groups[-1][1].extend(all_words[lo : hi + 1])
    if not groups:
        groups = [("", all_words[start_i : end_i + 1])]
    return [{"title": title, "sentences": split_sentences(words, transcript.speakers)} for title, words in groups]


def _snippet(words: list[Word]) -> str:
    text = " ".join(w.text for w in words[:SNIPPET_WORDS])
    return text + (" ..." if len(words) > SNIPPET_WORDS else "")


def neighbouring_beats(
    cut: Cut, index: TranscriptIndex, pending: Iterable[Suggestion], sync_group_id: str, start_i: int, end_i: int,
) -> list[dict]:
    """Beats (spans grouped by anchors, plus pending proposals) inside the scope and the
    `NEIGHBOURS_PER_SIDE` nearest on each side, in transcript order."""
    beats: dict[tuple[str, str], dict] = {}

    def slot(start_word_id: str, end_word_id: str, transcript_id: str) -> Optional[dict]:
        try:
            if index.sync_group_of(transcript_id) != sync_group_id:
                return None
            s = index.index_of(sync_group_id, start_word_id)
            e = index.index_of(sync_group_id, end_word_id)
        except KeyError:
            return None
        return beats.setdefault((start_word_id, end_word_id), {
            "start_word_id": start_word_id, "end_word_id": end_word_id, "_s": s, "_e": e, "_placed": False,
            "words": _snippet(index.words(sync_group_id)[s : e + 1]), "medium": None, "overlay": None,
            "brief": "", "status": "placed", "placed_by": "human",
        })

    for span in cut.spans:
        if span.orphaned or span.layer not in ("picture", "overlay"):
            continue
        beat = slot(span.start_anchor.word_id, span.end_anchor.word_id, span.start_anchor.transcript_id)
        if beat is None:
            continue
        beat["_placed"] = True
        if span.layer == "picture":
            beat["medium"] = span.kind
        elif span.overlay_depth:
            beat["overlay"] = {"depth": span.overlay_depth, "position": span.overlay_position}
        beat["brief"] = beat["brief"] or span.brief.text or span.note
        beat["placed_by"] = span.provenance
    for suggestion in pending:
        beat = slot(suggestion.start_anchor.word_id, suggestion.end_anchor.word_id, suggestion.start_anchor.transcript_id)
        if beat is None or beat["_placed"]:
            continue
        beat.update(status="proposed", placed_by="agent", medium=suggestion.medium, brief=suggestion.brief,
                    overlay={"depth": suggestion.overlay_depth, "position": suggestion.overlay_position}
                    if suggestion.overlay_depth else None)

    ordered = sorted(beats.values(), key=lambda b: (b["_s"], b["_e"]))
    before = [b for b in ordered if b["_e"] < start_i][-NEIGHBOURS_PER_SIDE:]
    inside = [b for b in ordered if b["_e"] >= start_i and b["_s"] <= end_i][:MAX_BEATS_INSIDE]
    after = [b for b in ordered if b["_s"] > end_i][:NEIGHBOURS_PER_SIDE]
    out = []
    for where, group in (("before", before), ("inside", inside), ("after", after)):
        for beat in group:
            out.append({"where": where, **{k: v for k, v in beat.items() if not k.startswith("_")}})
    return out


__all__ = ["split_sentences", "transcript_by_section", "neighbouring_beats"]
