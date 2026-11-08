"""EditSession: apply -> validate -> persist -> undo, including gesture coalescing."""
from __future__ import annotations

import pytest
from conftest import make_transcript

from post_core import store
from post_core.edit import ops
from post_core.edit.session import EditSession
from post_core.model import Rational
from post_core.store.undo import NothingToRedo, NothingToUndo

ASPECT = Rational(num=16, den=9)


def _setup_project(tmp_path):
    store.init_project(tmp_path)
    t = make_transcript("sg1", n=8)
    store.write(tmp_path, "transcript", t, expected_rev=0)
    cut = ops.cut_from_transcript(t, "cam-a", ASPECT)
    store.write(tmp_path, "cut", cut, expected_rev=0)
    return t, cut


def test_apply_persists_result_and_returns_report(tmp_path):
    t, cut = _setup_project(tmp_path)
    session = EditSession(tmp_path, cut.id)

    report = session.apply(lambda c, idx: ops.delete_words(c, idx, "sg1", t.words[2].id, t.words[3].id))
    assert report.orphaned_spans == []

    stored, rev = store.read(tmp_path, "cut", cut.id)
    assert rev == 2  # write #1 created the cut, apply() is write #2
    assert len(stored.passages) == 2


def test_undo_redo_round_trip(tmp_path):
    t, cut = _setup_project(tmp_path)
    session = EditSession(tmp_path, cut.id)
    session.apply(lambda c, idx: ops.delete_words(c, idx, "sg1", t.words[2].id, t.words[3].id))

    restored = session.undo()
    assert len(restored.passages) == 1
    assert restored.passages[0].start_word_id == cut.passages[0].start_word_id

    redone = session.redo()
    assert len(redone.passages) == 2

    with pytest.raises(NothingToRedo):
        session.redo()


def test_undo_with_no_history_raises(tmp_path):
    _t, cut = _setup_project(tmp_path)
    session = EditSession(tmp_path, cut.id)
    with pytest.raises(NothingToUndo):
        session.undo()


def test_gesture_coalesces_multiple_applies_into_one_undo_step(tmp_path):
    _t, cut = _setup_project(tmp_path)
    session = EditSession(tmp_path, cut.id)

    session.begin_gesture()
    session.apply(lambda c, idx: ops.set_trim(c, idx, c.passages[0].id, head=0.1, tail=0.0))
    session.apply(lambda c, idx: ops.set_trim(c, idx, c.passages[0].id, head=0.1, tail=0.1))
    session.end_gesture()

    stored, _rev = store.read(tmp_path, "cut", cut.id)
    assert stored.passages[0].trims.head == 0.1
    assert stored.passages[0].trims.tail == 0.1

    restored = session.undo()
    assert restored.passages[0].trims.head == 0.0
    assert restored.passages[0].trims.tail == 0.0

    with pytest.raises(NothingToUndo):
        session.undo()


def test_apply_rejects_invariant_violating_op(tmp_path):
    _t, cut = _setup_project(tmp_path)
    session = EditSession(tmp_path, cut.id)

    def bad_op(c, idx):
        from post_core.model import Passage

        bogus = c.model_copy(
            update={
                "passages": [
                    Passage(sync_group_id="sg1", start_word_id="does-not-exist", end_word_id="also-missing",
                             angle_source_id="cam-a")
                ]
            }
        )
        return bogus, ops.EditReport()

    with pytest.raises(Exception):
        session.apply(bad_op)

    # The store must be untouched by the rejected write.
    stored, rev = store.read(tmp_path, "cut", cut.id)
    assert rev == 1
    assert stored.passages[0].start_word_id == cut.passages[0].start_word_id
