"""Edit ops: word-addressed Cut->Cut transforms, span shrink/orphan behaviour, invariants."""
from __future__ import annotations

from conftest import make_transcript

from post_core.edit import ops
from post_core.edit.ranges import TranscriptIndex
from post_core.model import Cut, Passage, Rational, Span, WordAnchor
from post_core.store.invariants import validate_cut_invariants

ASPECT = Rational(num=16, den=9)


def test_cut_from_transcript_covers_all_words():
    t = make_transcript("sg1", n=6)
    cut = ops.cut_from_transcript(t, angle_source_id="cam-a", aspect=ASPECT)
    assert len(cut.passages) == 1
    assert cut.passages[0].start_word_id == t.words[0].id
    assert cut.passages[0].end_word_id == t.words[-1].id
    assert cut.passages[0].sync_group_id == "sg1"


def test_delete_words_splits_passage():
    t = make_transcript("sg1", n=8)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])

    new_cut, report = ops.delete_words(cut, index, "sg1", t.words[2].id, t.words[4].id)
    assert report == ops.EditReport()
    assert len(new_cut.passages) == 2
    assert new_cut.passages[0].end_word_id == t.words[1].id
    assert new_cut.passages[1].start_word_id == t.words[5].id
    validate_cut_invariants(new_cut, {t.id: t})


def test_delete_then_restore_is_identity():
    t = make_transcript("sg1", n=8)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])

    deleted, _ = ops.delete_words(cut, index, "sg1", t.words[2].id, t.words[4].id)
    restored, _ = ops.restore_words(deleted, index, "sg1", "cam-a", t.words[2].id, t.words[4].id, at=1)

    # merge_adjacent coalesces the restored range back into a single passage identical
    # (in word-range terms) to the original.
    assert len(restored.passages) == 1
    assert restored.passages[0].start_word_id == cut.passages[0].start_word_id
    assert restored.passages[0].end_word_id == cut.passages[0].end_word_id
    assert restored.passages[0].angle_source_id == cut.passages[0].angle_source_id


def test_delete_words_orphans_fully_covered_span():
    t = make_transcript("sg1", n=8)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    span = Span(
        layer="overlay",
        kind="lower-third",
        start_anchor=WordAnchor(transcript_id=t.id, word_id=t.words[3].id),
        end_anchor=WordAnchor(transcript_id=t.id, word_id=t.words[3].id),
    )
    cut = cut.model_copy(update={"spans": [span]})
    index = TranscriptIndex([t])

    new_cut, report = ops.delete_words(cut, index, "sg1", t.words[2].id, t.words[5].id)
    assert report.orphaned_spans == [span.id]
    assert report.affected_spans == []
    assert new_cut.spans[0].orphaned is True
    validate_cut_invariants(new_cut, {t.id: t})


def test_delete_words_shrinks_partially_covered_span():
    t = make_transcript("sg1", n=8)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    span = Span(
        layer="overlay",
        kind="lower-third",
        start_anchor=WordAnchor(transcript_id=t.id, word_id=t.words[1].id),
        end_anchor=WordAnchor(transcript_id=t.id, word_id=t.words[4].id),
    )
    cut = cut.model_copy(update={"spans": [span]})
    index = TranscriptIndex([t])

    # delete the leading edge of the span's range: it should shrink to what survives.
    new_cut, report = ops.delete_words(cut, index, "sg1", t.words[1].id, t.words[2].id)
    assert report.affected_spans == [span.id]
    assert report.orphaned_spans == []
    new_span = new_cut.spans[0]
    assert new_span.orphaned is False
    assert new_span.start_anchor.word_id == t.words[3].id
    assert new_span.end_anchor.word_id == t.words[4].id
    validate_cut_invariants(new_cut, {t.id: t})


def test_insert_range_can_unorphan_a_span():
    t = make_transcript("sg1", n=8)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    span = Span(
        layer="overlay",
        kind="lower-third",
        start_anchor=WordAnchor(transcript_id=t.id, word_id=t.words[3].id),
        end_anchor=WordAnchor(transcript_id=t.id, word_id=t.words[3].id),
    )
    cut = cut.model_copy(update={"spans": [span]})
    index = TranscriptIndex([t])

    orphaned_cut, report = ops.delete_words(cut, index, "sg1", t.words[2].id, t.words[5].id)
    assert report.orphaned_spans == [span.id]

    restored_cut, report2 = ops.insert_range(orphaned_cut, index, t.id, t.words[2].id, t.words[5].id, "cam-a", at=1)
    assert span.id in report2.affected_spans
    assert restored_cut.spans[0].orphaned is False


def test_move_passage_carries_spans_untouched():
    t1 = make_transcript("sg1", n=4)
    t2 = make_transcript("sg2", n=4)
    p1 = Passage(sync_group_id="sg1", start_word_id=t1.words[0].id, end_word_id=t1.words[-1].id, angle_source_id="cam-a")
    p2 = Passage(sync_group_id="sg2", start_word_id=t2.words[0].id, end_word_id=t2.words[-1].id, angle_source_id="cam-b")
    span = Span(
        layer="picture",
        kind="broll",
        start_anchor=WordAnchor(transcript_id=t1.id, word_id=t1.words[1].id),
        end_anchor=WordAnchor(transcript_id=t1.id, word_id=t1.words[2].id),
    )
    cut = Cut(aspect=ASPECT, passages=[p1, p2], spans=[span])
    index = TranscriptIndex([t1, t2])

    new_cut, report = ops.move_passage(cut, index, p1.id, at=1)
    assert [p.id for p in new_cut.passages] == [p2.id, p1.id]
    assert report.affected_spans == []
    assert report.orphaned_spans == []
    assert new_cut.spans[0].start_anchor.word_id == t1.words[1].id
    assert new_cut.spans[0].orphaned is False
    validate_cut_invariants(new_cut, {t1.id: t1, t2.id: t2})


def test_set_angle_splits_and_only_changes_target_range():
    t = make_transcript("sg1", n=6)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])

    new_cut, _ = ops.set_angle(cut, index, "sg1", t.words[2].id, t.words[3].id, "cam-b")
    assert len(new_cut.passages) == 3
    first, mid, last = new_cut.passages
    assert first.angle_source_id == "cam-a" and first.end_word_id == t.words[1].id
    assert mid.angle_source_id == "cam-b"
    assert mid.start_word_id == t.words[2].id and mid.end_word_id == t.words[3].id
    assert last.angle_source_id == "cam-a" and last.start_word_id == t.words[4].id
    validate_cut_invariants(new_cut, {t.id: t})


def test_replace_range_with_swaps_take():
    t1 = make_transcript("sg1", n=6)
    t2 = make_transcript("sg2", n=6)
    cut = ops.cut_from_transcript(t1, "cam-a", ASPECT)
    index = TranscriptIndex([t1, t2])

    new_cut, _ = ops.replace_range_with(
        cut, index, "sg1", t1.words[1].id, t1.words[3].id,
        "sg2", t2.words[0].id, t2.words[2].id, "cam-c",
    )
    assert any(p.sync_group_id == "sg2" and p.angle_source_id == "cam-c" for p in new_cut.passages)
    validate_cut_invariants(new_cut, {t1.id: t1, t2.id: t2})


def test_derive_cut_shares_word_ids_with_parent():
    t = make_transcript("sg1", n=6)
    parent = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])

    child, _report = ops.derive_cut(parent, index, [parent.passages[0].id], Rational(num=9, den=16))
    assert child.parent_cut_id == parent.id
    assert child.aspect == Rational(num=9, den=16)
    assert child.passages[0].start_word_id == parent.passages[0].start_word_id
    assert child.passages[0].end_word_id == parent.passages[0].end_word_id
    validate_cut_invariants(child, {t.id: t})


def test_op_sequence_keeps_invariants():
    t = make_transcript("sg1", n=12)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])
    transcripts = {t.id: t}

    cut, _ = ops.delete_words(cut, index, "sg1", t.words[3].id, t.words[4].id)
    validate_cut_invariants(cut, transcripts)
    cut, _ = ops.set_angle(cut, index, "sg1", t.words[6].id, t.words[7].id, "cam-b")
    validate_cut_invariants(cut, transcripts)
    cut, _ = ops.insert_range(cut, index, t.id, t.words[3].id, t.words[4].id, "cam-a", at=0)
    validate_cut_invariants(cut, transcripts)
    cut, _ = ops.move_passage(cut, index, cut.passages[-1].id, at=0)
    validate_cut_invariants(cut, transcripts)
    cut, _ = ops.set_trim(cut, index, cut.passages[0].id, head=0.05, tail=0.05)
    validate_cut_invariants(cut, transcripts)


# --- spans (T24) -------------------------------------------------------------------------

def test_add_span_appends_picture_span():
    t = make_transcript("sg1", n=8)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])

    new_cut, report = ops.add_span(
        cut, index, "sg1", t.words[2].id, t.words[4].id, layer="picture", kind="video", note="a detail",
    )
    assert report == ops.EditReport()
    assert len(new_cut.spans) == 1
    span = new_cut.spans[0]
    assert span.layer == "picture"
    assert span.kind == "video"
    assert span.note == "a detail"
    assert span.start_anchor.word_id == t.words[2].id
    assert span.end_anchor.word_id == t.words[4].id
    validate_cut_invariants(new_cut, {t.id: t})


def test_add_span_overlapping_same_layer_rejected_by_invariants():
    t = make_transcript("sg1", n=8)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])

    cut, _ = ops.add_span(cut, index, "sg1", t.words[0].id, t.words[3].id, layer="picture", kind="video")
    overlapping, _ = ops.add_span(cut, index, "sg1", t.words[2].id, t.words[5].id, layer="picture", kind="anim")
    with __import__("pytest").raises(Exception):
        validate_cut_invariants(overlapping, {t.id: t})


def test_remove_span_removes_by_id():
    t = make_transcript("sg1", n=8)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])
    cut, _ = ops.add_span(cut, index, "sg1", t.words[2].id, t.words[4].id, layer="picture", kind="video")
    span_id = cut.spans[0].id

    new_cut, report = ops.remove_span(cut, index, span_id)
    assert report == ops.EditReport()
    assert new_cut.spans == []
    validate_cut_invariants(new_cut, {t.id: t})


def test_remove_span_unknown_id_raises():
    t = make_transcript("sg1", n=4)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    index = TranscriptIndex([t])
    try:
        ops.remove_span(cut, index, "does-not-exist")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
