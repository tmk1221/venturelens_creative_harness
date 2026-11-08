"""MCP server for the VentureLens Creative Harness.

Exposes the transcript-first editing core (`post_core`) to LLM agents as a small set of
tools. Design rules, from reading the raw CLI's output as an agent would and from agent
evals (evals/EVALS.md):

1. Discoverable: one call (`get_project`) returns every id an agent needs next. The CLI's
   `project show` returned none of them.
2. Readable: cuts and transcripts come back as text with word ids at the edges, not bare
   ids. An agent can't edit what it can't read.
3. Few required inputs: sync groups and camera angles are derived from word ids, so the
   agent only ever passes ids it has already seen.
3b. The agent's units: move a sentence (move_words), build a short from sentences
   (make_short word ranges), one visual per accepted suggestion even when it has two layers.
4. Results include the new state, so an edit doesn't need a follow-up read.
5. Errors are structured: a stable `reason`, a plain message, and a `fix` naming the call
   that resolves it.
6. Safe to retry: creating a cut or a short with a label that already exists returns the
   existing one instead of making a duplicate.
7. No spend without a human: generation that costs money is not exposed here. Visual
   suggestions run in deterministic demo mode unless POST3_REAL=1.
"""
from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

if os.environ.get("POST3_REAL") != "1":
    os.environ.setdefault("POST3_FAKE_PROVIDERS", "1")

from post_core.edit import ops as ops_mod  # noqa: E402
from post_core.edit import suggest as suggest_mod  # noqa: E402
from post_core.edit.ranges import TranscriptIndex, passage_source_range  # noqa: E402
from post_core.edit.session import EditSession  # noqa: E402
from post_core.edit.suggest_context import split_sentences  # noqa: E402
from post_core.edit.suggest_store import read_suggestions  # noqa: E402
from post_core.edit._reconcile import covered_word_ids, reconcile_spans  # noqa: E402
from post_core.edit.ops import merge_adjacent  # noqa: E402
from post_core.model.common import Rational, WordAnchor  # noqa: E402
from post_core.model.cut import Cut, Passage  # noqa: E402
from post_core.store import store as store_module  # noqa: E402
from post_core.store.errors import InvariantError, NotFound, RevisionConflict, StoreError  # noqa: E402
from post_core.store.paths import store_root  # noqa: E402

mcp = FastMCP(
    "venturelens-creative-harness",
    instructions=(
        "Edit recorded interviews by editing their transcripts. Start with get_project(root) to see "
        "transcripts and cuts. A cut is an ordered list of passages (runs of words). Read a cut with "
        "read_cut, read source words with read_transcript (include_word_ids=true for word-level edits). "
        "Edit with remove_words, move_words (e.g. make a sentence the opening line), restore_words and "
        "move_passage; undo_edit reverts the last edit. make_short builds a vertical short from word ranges "
        "(e.g. chosen sentences). suggest_visuals proposes B-roll and "
        "graphics; accept_visual adds one to the cut. export_timeline writes a DaVinci Resolve timeline."
    ),
)


# --- errors ------------------------------------------------------------------------------

def _fail(reason: str, message: str, fix: str) -> ToolError:
    return ToolError(json.dumps({"reason": reason, "message": message, "fix": fix}))


def _guard(fn):
    """Turn core exceptions into structured tool errors with a next step."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except NotFound as exc:
            raise _fail("not_found", str(exc), "Call get_project(root) to list valid ids.") from exc
        except RevisionConflict as exc:
            raise _fail("conflict", str(exc), "Someone else changed this cut. Call read_cut and retry.") from exc
        except InvariantError as exc:
            raise _fail("invalid_edit", str(exc), "Read the cut again; the edit would leave it in an invalid state.") from exc
        except suggest_mod.SuggestError as exc:
            raise _fail("suggestion_error", str(exc), "Call suggest_visuals again to get current suggestion ids.") from exc
        except StoreError as exc:
            raise _fail("store_error", str(exc), "Check the project root path with get_project.") from exc

    return wrapper


# --- loading helpers ---------------------------------------------------------------------

def _root(root: str) -> Path:
    p = Path(root).expanduser().resolve()
    if not (store_root(p) / "project.json").is_file():
        raise _fail(
            "not_a_project",
            f"{p} is not a Creative Harness project (no .post3/project.json).",
            "Pass the project folder, e.g. the path printed by scripts/make_demo_project.py.",
        )
    return p


def _all(root: Path, kind_dir: str, kind: str) -> list:
    d = store_root(root) / kind_dir
    out = []
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            if "." in f.stem:  # sidecars like <id>.undo.json / <id>.suggestions.json
                continue
            obj, _rev = store_module.read(root, kind, f.stem)
            out.append(obj)
    return out


def _transcripts(root: Path) -> list:
    return _all(root, "transcripts", "transcript")


def _index(root: Path) -> TranscriptIndex:
    return TranscriptIndex(_transcripts(root))


def _locate_word(root: Path, word_id: str) -> tuple[Any, int]:
    """(transcript, position) for a word id, from any transcript in the project."""
    for t in _transcripts(root):
        for i, w in enumerate(t.words):
            if w.id == word_id:
                return t, i
    raise _fail(
        "unknown_word_id",
        f"No word with id {word_id!r} in this project.",
        "Call read_transcript(root, transcript_id, include_word_ids=true) and copy ids from it.",
    )


def _angle_for(root: Path, sync_group_id: str) -> str:
    """The camera angle to use when the agent doesn't name one: the a_roll source of the
    sync group, else its first source."""
    for shoot in _all(root, "shoots", "shoot"):
        for group in shoot.sync_groups:
            if group.id == sync_group_id:
                by_id = {s.id: s for s in shoot.sources}
                a_rolls = [sid for sid in group.source_ids if by_id[sid].role == "a_roll"]
                return (a_rolls or group.source_ids)[0]
    raise _fail("no_source", f"No recording found for sync group {sync_group_id!r}.", "Call get_project(root).")


def _aspect(raw: str) -> Rational:
    try:
        num, den = raw.split(":", 1)
        return Rational(num=int(num), den=int(den))
    except (ValueError, AttributeError) as exc:
        raise _fail("bad_aspect", f"Aspect {raw!r} is not like '16:9'.", "Use '16:9', '9:16', '4:5' or '1:1'.") from exc


def _words_text(index: TranscriptIndex, sync_group_id: str, start_id: str, end_id: str) -> str:
    words = index.words(sync_group_id)
    a, b = index.index_of(sync_group_id, start_id), index.index_of(sync_group_id, end_id)
    return " ".join(w.text for w in words[a : b + 1])


def _cut_view(root: Path, cut_id: str) -> dict:
    cut, revision = store_module.read(root, "cut", cut_id)
    index = _index(root)
    passages, total = [], 0.0
    for i, p in enumerate(cut.passages):
        start, end = passage_source_range(p, index)
        total += end - start
        passages.append({
            "index": i,
            "passage_id": p.id,
            "text": _words_text(index, p.sync_group_id, p.start_word_id, p.end_word_id),
            "first_word_id": p.start_word_id,
            "last_word_id": p.end_word_id,
            "seconds": round(end - start, 1),
        })
    # One visual per beat: a picture span and the overlay span sharing its anchors are one
    # thing to an agent (it accepted one suggestion), not two. Eval T5 baseline.
    beats: dict[tuple, dict] = {}
    for s in cut.spans:
        key = (s.start_anchor.transcript_id, s.start_anchor.word_id, s.end_anchor.word_id)
        try:
            covered = _words_text(index, index.sync_group_of(s.start_anchor.transcript_id),
                                  s.start_anchor.word_id, s.end_anchor.word_id)
        except KeyError:
            covered = ""
        beat = beats.setdefault(key, {"visual_id": s.id, "picture": None, "overlay": None, "brief": "",
                                      "over_words": covered, "orphaned": False})
        if s.layer == "overlay":
            beat["overlay"] = f"{s.overlay_depth} {s.overlay_position}".replace("_", " ")
        else:
            beat["visual_id"], beat["picture"] = s.id, s.kind
        beat["brief"] = beat["brief"] or s.brief.text
        beat["orphaned"] = beat["orphaned"] or s.orphaned
    visuals = list(beats.values())
    aspect = f"{cut.aspect.num}:{cut.aspect.den}"
    return {"cut_id": cut.id, "label": cut.variant_label, "aspect": aspect, "parent_cut_id": cut.parent_cut_id,
            "revision": revision, "seconds": round(total, 1), "passages": passages, "visuals": visuals}


def _find_cut_by_label(root: Path, label: str, parent_or_transcript: Optional[str] = None) -> Optional[str]:
    if not label:
        return None
    for cut in _all(root, "cuts", "cut"):
        if cut.variant_label == label:
            return cut.id
    return None


# --- tools: discover and read ------------------------------------------------------------

@mcp.tool()
@_guard
def get_project(root: str) -> dict:
    """Overview of a project: its recordings, transcripts and cuts, with every id you need for
    the other tools. Call this first. `root` is the project folder path."""
    r = _root(root)
    project, _ = store_module.read(r, "project")
    sources = []
    for shoot in _all(r, "shoots", "shoot"):
        for s in shoot.sources:
            sources.append({"source_id": s.id, "role": s.role, "file": Path(s.path).name if s.path else None})
    transcripts = []
    for t in _transcripts(r):
        transcripts.append({
            "transcript_id": t.id, "words": len(t.words),
            "seconds": round(t.words[-1].end - t.words[0].start, 1) if t.words else 0,
            "speakers": sorted({t.speakers.get(w.speaker, w.speaker) for w in t.words if w.speaker}),
        })
    cuts = []
    for c in _all(r, "cuts", "cut"):
        cuts.append({"cut_id": c.id, "label": c.variant_label, "aspect": f"{c.aspect.num}:{c.aspect.den}",
                     "parent_cut_id": c.parent_cut_id, "passages": len(c.passages), "visuals": len(c.spans)})
    return {"name": project.name, "brand_kit": project.brand_kit, "sources": sources,
            "transcripts": transcripts, "cuts": cuts}


@mcp.tool()
@_guard
def read_transcript(root: str, transcript_id: str, from_sentence: int = 0, max_sentences: int = 40,
                    include_word_ids: bool = False) -> dict:
    """The source transcript as numbered sentences (speaker, time, text, first/last word id).
    Set include_word_ids=true to get every word's id, needed to remove or restore part of a
    sentence. Use from_sentence/max_sentences to page through long transcripts."""
    r = _root(root)
    t, _ = store_module.read(r, "transcript", transcript_id)
    sentences = split_sentences(t.words, t.speakers)
    by_id = {w.id: w for w in t.words}
    out = []
    for n, s in enumerate(sentences[from_sentence : from_sentence + max_sentences], start=from_sentence):
        first, last = by_id[s["words"][0]["id"]], by_id[s["words"][-1]["id"]]
        item = {"n": n, "speaker": s["speaker"], "start_s": round(first.start, 1), "end_s": round(last.end, 1),
                "text": " ".join(w["text"] for w in s["words"]),
                "first_word_id": first.id, "last_word_id": last.id}
        if include_word_ids:
            item["words"] = [[w["id"], w["text"]] for w in s["words"]]
        out.append(item)
    return {"transcript_id": t.id, "total_sentences": len(sentences), "sentences": out}


@mcp.tool()
@_guard
def read_cut(root: str, cut_id: str) -> dict:
    """A cut as it plays: ordered passages with their text, length and first/last word ids,
    plus the visuals (B-roll, graphics) placed over it."""
    return _cut_view(_root(root), cut_id)


# --- tools: edit -------------------------------------------------------------------------

@mcp.tool()
@_guard
def create_cut(root: str, transcript_id: str, aspect: str = "16:9", label: str = "") -> dict:
    """A new cut containing the whole transcript, ready to edit down. If a cut with the same
    label already exists it is returned instead (safe to retry)."""
    r = _root(root)
    existing = _find_cut_by_label(r, label)
    if existing:
        return {"created": False, **_cut_view(r, existing)}
    t, _ = store_module.read(r, "transcript", transcript_id)
    cut = ops_mod.cut_from_transcript(t, _angle_for(r, t.sync_group_id), _aspect(aspect))
    if label:
        cut = cut.model_copy(update={"variant_label": label})
    store_module.write(r, "cut", cut, expected_rev=0)
    return {"created": True, **_cut_view(r, cut.id)}


def _apply(r: Path, cut_id: str, op_fn) -> dict:
    store_module.read(r, "cut", cut_id)  # NotFound before any work
    report = EditSession(r, cut_id).apply(op_fn)
    view = _cut_view(r, cut_id)
    view["visuals_affected"] = report.affected_spans
    view["visuals_orphaned"] = report.orphaned_spans
    return view


@mcp.tool()
@_guard
def remove_words(root: str, cut_id: str, first_word_id: str, last_word_id: str) -> dict:
    """Cut a run of words (inclusive) out of the cut, e.g. a filler, a false start or a whole
    sentence. Word ids come from read_cut or read_transcript. Returns the updated cut."""
    r = _root(root)
    t1, i1 = _locate_word(r, first_word_id)
    t2, i2 = _locate_word(r, last_word_id)
    if t1.id != t2.id:
        raise _fail("mixed_transcripts", "First and last word are in different transcripts.",
                    "Remove the range from each transcript separately.")
    if i1 > i2:
        raise _fail("reversed_range", "first_word_id comes after last_word_id.", "Swap the two ids.")
    op = functools.partial(ops_mod.delete_words, sync_group_id=t1.sync_group_id,
                           start_word_id=first_word_id, end_word_id=last_word_id)
    return _apply(r, cut_id, op)


@mcp.tool()
@_guard
def restore_words(root: str, cut_id: str, first_word_id: str, last_word_id: str, at_index: int) -> dict:
    """Put a run of source words back into the cut as a passage at position `at_index`
    (0 = first). Use it to bring back something removed, or to pull in a different take."""
    r = _root(root)
    t1, i1 = _locate_word(r, first_word_id)
    t2, i2 = _locate_word(r, last_word_id)
    if t1.id != t2.id or i1 > i2:
        raise _fail("bad_range", "The two word ids must be in one transcript, first before last.",
                    "Copy both ids from one read_transcript call.")
    op = functools.partial(ops_mod.restore_words, sync_group_id=t1.sync_group_id,
                           angle_source_id=_angle_for(r, t1.sync_group_id),
                           start_word_id=first_word_id, end_word_id=last_word_id, at=at_index)
    return _apply(r, cut_id, op)


@mcp.tool()
@_guard
def move_passage(root: str, cut_id: str, passage_id: str, to_index: int) -> dict:
    """Move one passage to a new position (0 = first). Passage ids change after edits, so take
    them from the most recent read_cut or edit result."""
    r = _root(root)
    cut, _ = store_module.read(r, "cut", cut_id)
    if passage_id not in {p.id for p in cut.passages}:
        raise _fail("unknown_passage_id", f"Cut has no passage {passage_id!r}; ids change after every edit.",
                    "Call read_cut and use a current passage_id.")
    op = functools.partial(ops_mod.move_passage, passage_id=passage_id, at=to_index)
    return _apply(r, cut_id, op)


@mcp.tool()
@_guard
def move_words(root: str, cut_id: str, first_word_id: str, last_word_id: str, before_word_id: str = "") -> dict:
    """Move a run of words (e.g. one sentence) so it plays just before `before_word_id`, or at
    the end of the cut if that is empty. Use the first word of the cut as before_word_id to
    make something the opening line. One edit, one undo step."""
    r = _root(root)
    t1, i1 = _locate_word(r, first_word_id)
    t2, i2 = _locate_word(r, last_word_id)
    if t1.id != t2.id or i1 > i2:
        raise _fail("bad_range", "The two word ids must be in one transcript, first before last.",
                    "Copy both ids from one read_transcript or read_cut call.")
    anchor = None
    if before_word_id:
        tb, _ = _locate_word(r, before_word_id)
        anchor = WordAnchor(transcript_id=tb.id, word_id=before_word_id)
    op = functools.partial(ops_mod.move_words, sync_group_id=t1.sync_group_id, start_word_id=first_word_id,
                           end_word_id=last_word_id, before_word=anchor)
    try:
        return _apply(r, cut_id, op)
    except ValueError as exc:
        raise _fail("words_not_in_cut", str(exc), "Only words currently in the cut can move; check read_cut.") from exc


@mcp.tool()
@_guard
def undo_edit(root: str, cut_id: str) -> dict:
    """Revert the most recent edit to this cut. Returns the cut after the undo."""
    r = _root(root)
    EditSession(r, cut_id).undo()
    return _cut_view(r, cut_id)


@mcp.tool()
@_guard
def make_short(root: str, cut_id: str, word_ranges: list[list[str]], aspect: str = "9:16",
               label: str = "") -> dict:
    """A new cut (e.g. a vertical social short) made from parts of an existing cut, in the
    order given. Each item of word_ranges is [first_word_id, last_word_id], e.g. the first and
    last word ids of the sentences you want (from read_transcript). The parent cut is
    unchanged and visuals over kept words come along. Same label twice returns the existing
    short (safe to retry)."""
    r = _root(root)
    existing = _find_cut_by_label(r, label)
    if existing:
        return {"created": False, **_cut_view(r, existing)}
    parent, _ = store_module.read(r, "cut", cut_id)
    transcripts = _transcripts(r)
    index = TranscriptIndex(transcripts)
    in_parent = covered_word_ids(parent.passages, index)
    passages = []
    for pair in word_ranges:
        if not (isinstance(pair, list) and len(pair) == 2):
            raise _fail("bad_range", f"Each range must be [first_word_id, last_word_id]; got {pair!r}.",
                        "Pass e.g. [[\"<first id>\", \"<last id>\"], ...].")
        t1, i1 = _locate_word(r, pair[0])
        t2, i2 = _locate_word(r, pair[1])
        if t1.id != t2.id or i1 > i2:
            raise _fail("bad_range", f"Range {pair!r}: ids must be in one transcript, first before last.",
                        "Copy both ids from one read_transcript call.")
        kept = in_parent.get(t1.sync_group_id, set())
        outside = [w.text for w in t1.words[i1 : i2 + 1] if w.id not in kept]
        if outside:
            raise _fail("words_not_in_cut", f"Range {pair!r} includes words not in the parent cut: "
                        f"{' '.join(outside[:8])}", "Pick ranges from read_cut of the parent, or restore them first.")
        passages.append(Passage(sync_group_id=t1.sync_group_id, start_word_id=pair[0], end_word_id=pair[1],
                                angle_source_id=_angle_for(r, t1.sync_group_id)))
    if not passages:
        raise _fail("empty_short", "word_ranges is empty.", "Pass at least one [first_word_id, last_word_id].")
    draft = Cut(aspect=_aspect(aspect), parent_cut_id=parent.id, variant_label=label, passages=passages,
                spans=[s.model_copy(deep=True) for s in parent.spans], sections=[])
    spans, _report = reconcile_spans(draft.spans, index, covered_word_ids(passages, index))
    derived = merge_adjacent(draft.model_copy(update={"spans": spans}), index)
    store_module.write(r, "cut", derived, expected_rev=0)
    return {"created": True, **_cut_view(r, derived.id)}


# --- tools: visuals and export -----------------------------------------------------------

@mcp.tool()
@_guard
def suggest_visuals(root: str, cut_id: str, first_word_id: str = "", last_word_id: str = "") -> dict:
    """Propose visuals (B-roll, motion graphics, overlays) for the whole cut, or only for the
    words between first_word_id and last_word_id. Proposals are pending until accept_visual.
    Runs replace earlier pending proposals in the same range."""
    r = _root(root)
    cut, _ = store_module.read(r, "cut", cut_id)
    if not cut.passages:
        raise _fail("empty_cut", "The cut has no passages.", "Restore words first, or pick another cut.")
    if first_word_id and last_word_id:
        t, _ = _locate_word(r, first_word_id)
        scope = suggest_mod.Scope(kind="selection", sync_group_id=t.sync_group_id,
                                  start_word_id=first_word_id, end_word_id=last_word_id)
    else:
        first, last = cut.passages[0], cut.passages[-1]
        scope = suggest_mod.Scope(kind="cut", sync_group_id=first.sync_group_id,
                                  start_word_id=first.start_word_id, end_word_id=last.end_word_id)
    items = suggest_mod.suggest_visuals(r, cut_id, _transcripts(r), scope, cut=cut)
    index = _index(r)
    out = []
    for s in items:
        sg = index.sync_group_of(s.start_anchor.transcript_id)
        overlay = (f"{s.overlay_depth} {s.overlay_position}".replace("_", " ")
                   if s.overlay_depth else None)
        out.append({"suggestion_id": s.id, "picture": s.medium, "overlay": overlay, "brief": s.brief,
                    "why": s.rationale,
                    "over_words": _words_text(index, sg, s.start_anchor.word_id, s.end_anchor.word_id)})
    return {"cut_id": cut_id, "mode": "demo" if os.environ.get("POST3_FAKE_PROVIDERS") == "1" else "agent",
            "pending": out}


@mcp.tool()
@_guard
def accept_visual(root: str, cut_id: str, suggestion_id: str) -> dict:
    """Add one pending suggestion to the cut as a visual. Returns the updated cut."""
    r = _root(root)
    pending = {s.id for s in read_suggestions(r, cut_id).items}
    if suggestion_id not in pending:
        raise _fail("unknown_suggestion_id", f"No pending suggestion {suggestion_id!r} on this cut.",
                    "Call suggest_visuals(root, cut_id) and use an id from its result.")
    suggest_mod.accept_suggestion(r, cut_id, suggestion_id)
    return _cut_view(r, cut_id)


@mcp.tool()
@_guard
def export_timeline(root: str, cut_id: str) -> dict:
    """Write the cut as an OpenTimelineIO (.otio) timeline that DaVinci Resolve imports, with
    each visual on its own track. Returns the file path."""
    r = _root(root)
    try:
        from post_core.export import otio_export
    except ImportError as exc:
        raise _fail("export_unavailable", "opentimelineio is not installed.",
                    "pip install opentimelineio, then retry.") from exc
    try:
        path = otio_export.export_cut(r, cut_id)
    except otio_export.ExportError as exc:
        raise _fail("export_failed", str(exc), "Check the cut with read_cut; every passage needs source media.") from exc
    return {"cut_id": cut_id, "path": str(path)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
