"""Store: round-trip, revision conflicts, concurrent writers, corrupt-file refusal, invariants."""
from __future__ import annotations

import fcntl
import multiprocessing
import os
import threading
from pathlib import Path

import pytest

from post_core import store
from post_core.model import (
    Cut,
    Passage,
    Project,
    Rational,
    Shoot,
    Source,
    Span,
    SyncGroup,
    Transcript,
    Word,
    WordAnchor,
)
from post_core.store.errors import CorruptFile, InvariantError, NotFound, RevisionConflict


def make_source(**kw) -> Source:
    defaults = dict(path="/media/cam-a.mov", fps=Rational(num=30, den=1),
                     start_timecode="00:00:00:00", content_fingerprint="fp-a")
    defaults.update(kw)
    return Source(**defaults)


# --- round trip -------------------------------------------------------------------------

def test_round_trip(tmp_path: Path):
    store.init_project(tmp_path)
    source = make_source()
    shoot = Shoot(name="Day 1", sources=[source])
    revision = store.write(tmp_path, "shoot", shoot, expected_rev=0)
    assert revision == 1

    loaded, loaded_rev = store.read(tmp_path, "shoot", shoot.id)
    assert loaded_rev == 1
    assert loaded.name == "Day 1"
    assert loaded.sources[0].path == "/media/cam-a.mov"
    assert loaded.id == shoot.id


def test_read_missing_raises_not_found(tmp_path: Path):
    store.init_project(tmp_path)
    with pytest.raises(NotFound):
        store.read(tmp_path, "shoot", "does-not-exist")


# --- revision conflict -------------------------------------------------------------------

def test_revision_conflict_on_stale_write(tmp_path: Path):
    store.init_project(tmp_path)
    shoot = Shoot(name="Day 1")
    store.write(tmp_path, "shoot", shoot, expected_rev=0)

    # A second writer, still holding the old (0) expected revision, must be refused.
    with pytest.raises(RevisionConflict):
        store.write(tmp_path, "shoot", shoot, expected_rev=0)

    # The correct next revision succeeds.
    shoot.name = "Day 1 (renamed)"
    new_rev = store.write(tmp_path, "shoot", shoot, expected_rev=1)
    assert new_rev == 2


def test_write_new_object_requires_expected_rev_zero(tmp_path: Path):
    store.init_project(tmp_path)
    shoot = Shoot(name="Day 1")
    with pytest.raises(RevisionConflict):
        store.write(tmp_path, "shoot", shoot, expected_rev=1)


# --- corrupt file refusal ----------------------------------------------------------------

def test_corrupt_file_is_refused_not_overwritten(tmp_path: Path):
    store.init_project(tmp_path)
    shoot = Shoot(name="Day 1")
    store.write(tmp_path, "shoot", shoot, expected_rev=0)

    path = store.object_path(tmp_path, "shoot", shoot.id)
    path.write_text("not json at all {{{", encoding="utf-8")

    with pytest.raises(CorruptFile):
        store.read(tmp_path, "shoot", shoot.id)
    # A write attempt must also refuse rather than blindly clobber the corrupt file.
    with pytest.raises(CorruptFile):
        store.write(tmp_path, "shoot", shoot, expected_rev=1)
    # The corrupt bytes are untouched.
    assert path.read_text(encoding="utf-8") == "not json at all {{{"


def test_malformed_envelope_is_refused(tmp_path: Path):
    store.init_project(tmp_path)
    path = store.object_path(tmp_path, "shoot", "some-id")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"revision": 1}', encoding="utf-8")  # missing "data"
    with pytest.raises(CorruptFile):
        store.read(tmp_path, "shoot", "some-id")


# --- concurrent writers --------------------------------------------------------------------

def _increment_project_name(project_root: str, attempts: int) -> None:
    for _ in range(attempts):
        while True:
            obj, rev = store.read(project_root, "project")
            try:
                store.write(project_root, "project",
                            obj.model_copy(update={"name": str(int(obj.name) + 1)}), rev)
                break
            except RevisionConflict:
                continue


def test_concurrent_writers_do_not_lose_updates(tmp_path: Path):
    store.init_project(tmp_path)
    store.write(tmp_path, "project", Project(name="0", root=str(tmp_path)), expected_rev=0)

    n_procs, attempts = 4, 10
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_increment_project_name, args=(str(tmp_path), attempts))
             for _ in range(n_procs)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=60)
        assert p.exitcode == 0

    final, _ = store.read(tmp_path, "project")
    assert int(final.name) == n_procs * attempts


# --- invariants --------------------------------------------------------------------------

def _seed_transcript(tmp_path: Path, sync_group_id: str = "sg1") -> Transcript:
    words = [
        Word(id="w1", text="hello", start=0.0, end=0.5),
        Word(id="w2", text="world", start=0.5, end=1.0),
        Word(id="w3", text="today", start=1.0, end=1.5),
    ]
    transcript = Transcript(sync_group_id=sync_group_id, provider="test", words=words, fingerprint="fp")
    store.write(tmp_path, "transcript", transcript, expected_rev=0)
    return transcript


def test_cut_write_rejects_passage_with_unknown_word(tmp_path: Path):
    store.init_project(tmp_path)
    _seed_transcript(tmp_path)
    passage = Passage(sync_group_id="sg1", start_word_id="w1", end_word_id="missing", angle_source_id="s1")
    cut = Cut(aspect=Rational(num=16, den=9), passages=[passage])
    with pytest.raises(InvariantError):
        store.write(tmp_path, "cut", cut, expected_rev=0)


def test_cut_write_rejects_passage_out_of_order(tmp_path: Path):
    store.init_project(tmp_path)
    _seed_transcript(tmp_path)
    passage = Passage(sync_group_id="sg1", start_word_id="w3", end_word_id="w1", angle_source_id="s1")
    cut = Cut(aspect=Rational(num=16, den=9), passages=[passage])
    with pytest.raises(InvariantError):
        store.write(tmp_path, "cut", cut, expected_rev=0)


def test_cut_write_accepts_valid_passage(tmp_path: Path):
    store.init_project(tmp_path)
    transcript = _seed_transcript(tmp_path)
    passage = Passage(sync_group_id="sg1", start_word_id="w1", end_word_id="w3", angle_source_id="s1")
    cut = Cut(aspect=Rational(num=16, den=9), passages=[passage])
    rev = store.write(tmp_path, "cut", cut, expected_rev=0)
    assert rev == 1
    loaded, _ = store.read(tmp_path, "cut", cut.id)
    assert loaded.passages[0].start_word_id == "w1"
    assert transcript.sync_group_id == "sg1"


def test_cut_write_rejects_overlapping_spans_on_same_layer(tmp_path: Path):
    store.init_project(tmp_path)
    transcript = _seed_transcript(tmp_path)
    span_a = Span(layer="overlay", kind="lower_third",
                  start_anchor=WordAnchor(transcript_id=transcript.id, word_id="w1"),
                  end_anchor=WordAnchor(transcript_id=transcript.id, word_id="w2"))
    span_b = Span(layer="overlay", kind="lower_third",
                  start_anchor=WordAnchor(transcript_id=transcript.id, word_id="w2"),
                  end_anchor=WordAnchor(transcript_id=transcript.id, word_id="w3"))
    cut = Cut(aspect=Rational(num=16, den=9), spans=[span_a, span_b])
    with pytest.raises(InvariantError):
        store.write(tmp_path, "cut", cut, expected_rev=0)


def test_cut_write_rejects_span_with_unresolvable_anchor(tmp_path: Path):
    store.init_project(tmp_path)
    _seed_transcript(tmp_path)
    span = Span(layer="picture", kind="broll",
                start_anchor=WordAnchor(transcript_id="no-such-transcript", word_id="w1"),
                end_anchor=WordAnchor(transcript_id="no-such-transcript", word_id="w2"))
    cut = Cut(aspect=Rational(num=16, den=9), spans=[span])
    with pytest.raises(InvariantError):
        store.write(tmp_path, "cut", cut, expected_rev=0)


# --- T23: reads must not hold the object's file lock across a request -----------------

def test_read_does_not_block_on_an_externally_held_lock(tmp_path: Path):
    """Regression for the 2026-09-21 bug: an idle uvicorn worker held `cuts/<id>.json.lock`
    and blocked an external writer (an import script) for ~10 minutes. `read()` must never
    take that lock -- so a read must complete even while something else (simulating a
    stuck/idle request holding the lock, or the lock file simply being flocked by another
    process) is holding an exclusive flock on the object's `.lock` file."""
    store.init_project(tmp_path)
    shoot = Shoot(name="Day 1")
    store.write(tmp_path, "shoot", shoot, expected_rev=0)
    lock_file = store.object_path(tmp_path, "shoot", shoot.id).with_suffix(".json.lock")

    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        done = threading.Event()

        def do_read():
            store.read(tmp_path, "shoot", shoot.id)
            done.set()

        t = threading.Thread(target=do_read)
        t.start()
        t.join(timeout=2.0)
        assert done.is_set(), "store.read() blocked on an externally held lock"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_request_read_then_external_write_does_not_block(tmp_path: Path):
    """A 'request' that only reads (e.g. a GET handler) must leave the lock free the moment
    it returns, so a completely separate writer (e.g. an import script writing straight to
    disk, as `scripts/make_acme_script_demo.py`/`import_acme_demo.py` do) is never
    blocked by it."""
    store.init_project(tmp_path)
    shoot = Shoot(name="Day 1")
    rev = store.write(tmp_path, "shoot", shoot, expected_rev=0)

    # Simulate a request: read the object (this used to also acquire the flock).
    store.read(tmp_path, "shoot", shoot.id)

    done = threading.Event()

    def external_write():
        store.write(tmp_path, "shoot", shoot.model_copy(update={"name": "Day 1 (renamed)"}), expected_rev=rev)
        done.set()

    t = threading.Thread(target=external_write)
    t.start()
    t.join(timeout=2.0)
    assert done.is_set(), "external write blocked after a plain read"


def test_cut_write_accepts_non_overlapping_spans(tmp_path: Path):
    store.init_project(tmp_path)
    transcript = _seed_transcript(tmp_path)
    span_a = Span(layer="overlay", kind="lower_third",
                  start_anchor=WordAnchor(transcript_id=transcript.id, word_id="w1"),
                  end_anchor=WordAnchor(transcript_id=transcript.id, word_id="w1"))
    span_b = Span(layer="overlay", kind="lower_third",
                  start_anchor=WordAnchor(transcript_id=transcript.id, word_id="w3"),
                  end_anchor=WordAnchor(transcript_id=transcript.id, word_id="w3"))
    cut = Cut(aspect=Rational(num=16, den=9), spans=[span_a, span_b])
    rev = store.write(tmp_path, "cut", cut, expected_rev=0)
    assert rev == 1
