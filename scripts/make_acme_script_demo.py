#!/usr/bin/env python3
"""T24: build a "post-picture-lock" RAW transcript demo at `.demo-script/`.

Decision (Travis, 2026-09-22): for now Post is used AFTER picture lock in Resolve. It shows
the transcript and is where the viewer's visuals are decided; it never plays audio or video.
For this demo we treat the actual Acme Automations SCRIPT
(`~/cc/smb_automations/synthesis/MEGA-CUT.md`) as if it were spoken -- not a real Deepgram
transcript -- with word timings synthesised at a deterministic rate.

T24 supersedes T23's structured (Sections/story-markers) output: Travis's read on T23 was
"wrong content" -- pre-structuring the script into chapters is exactly how the previous app
over-fit. This script keeps the SAME parse (it still knows which lines of the script are
spoken vs. stage direction) but throws the structure away: the emitted Cut has ONE passage
covering every word, in document order, and no Sections at all -- a single continuous
transcript, exactly like a real Deepgram transcript of one continuous take. The web layer
derives its own paragraph breaks from long pauses in the word timings (see
`web/src/edit/rawTranscript.ts`), not from any server-side heading.

READ-ONLY inputs (AGENTS.md / tasks/T23.md): this script only ever reads
`~/cc/smb_automations/synthesis/MEGA-CUT.md`. It does not import from
`~/cc/vl/scripts/acme-automations/units.py` (that script belongs to a different,
actively-worked-on repo) -- the parse rules below are a deliberate, minimal port of that
file's logic, copied in rather than imported, per tasks/T23.md. No network, no paid calls,
never touches DaVinci Resolve, nothing under `/Volumes` or `~/cc/post`/`~/cc/vl`/`~/cc/post-*`
is written to.

Output: `.demo-script/` (gitignored) -- a real post3 project on disk, built directly through
`post_core.store` (like `scripts/import_acme_demo.py`), with:
  - one Shoot holding a single `kind="virtual"` Source (`path=None`, no media at all) and one
    SyncGroup around it
  - one Transcript of synthesised words for that sync group
  - one master Cut with a single Passage over every word and an empty `sections` list --
    the "raw transcript" the T24 spec calls for. Word timings still carry a longer pause
    (`SECTION_PAUSE`) at what were the old top-level boundaries (Intro / segment change /
    Close) and a shorter pause (`STORY_PAUSE`) between stories within a segment, purely so
    the web layer's pause-based paragraphing reads naturally -- neither pause is a heading.

Usage (also wired as `make demo-script`):
    packages/post_core/.venv/bin/python scripts/make_acme_script_demo.py [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "post_core"))

from post_core.model.common import Rational  # noqa: E402
from post_core.model.cut import Cut, Passage  # noqa: E402
from post_core.model.project import Project  # noqa: E402
from post_core.model.shoot import Shoot, Source, SyncGroup  # noqa: E402
from post_core.model.transcript import Transcript, Word  # noqa: E402
from post_core.store import store as store_module  # noqa: E402
from post_core.store.paths import store_root  # noqa: E402

SCRIPT_PATH = Path.home() / "cc" / "smb_automations" / "synthesis" / "MEGA-CUT.md"
PROJECT_ROOT = REPO_ROOT / ".demo-script"
PROJECT_NAME = "Acme Automations — script demo"

WORDS_PER_SECOND = 2.6
WORD_DURATION = 1.0 / WORDS_PER_SECOND
STORY_PAUSE = 0.6   # between stories (and Close -> CTA, folded as an extra in-section beat)
SECTION_PAUSE = 1.5  # between Intro/segment/Close boundaries

SEGMENT_GLYPHS = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5, "⑥": 6, "⑦": 7}

STORY_RE = re.compile(r"^###\s+Automation\s+(\d+)\s*[—–-]\s*(.+?)\s*$")
H2_RE = re.compile(r"^##\s+(.+?)\s*$")
STATUS_GLYPHS = "⬜🎥✅"


# --- parsing (ported from ~/cc/vl/scripts/acme-automations/units.py, not imported) ------

def _clean_heading(h: str) -> str:
    return "".join(ch for ch in h if ch not in STATUS_GLYPHS).strip()


def _is_direction(line: str) -> bool:
    """On-screen flashes, italic stage notes, rules -- not spoken."""
    s = line.strip()
    return (
        s.startswith("**[") or s.startswith("[") or s.startswith("_(") or s.startswith("(")
        or s == "---" or (s.startswith("*") and not s.startswith("**"))
    )


def _spoken(line: str) -> Optional[str]:
    s = line.strip()
    if not s or _is_direction(s):
        return None
    s = re.sub(r"^(-|\*|\d+\.)\s+", "", s)  # list markers are read, not shown
    s = s.replace("**", "")
    s = re.sub(r"\s+", " ", s)
    return s or None


class Unit:
    def __init__(self, kind: str, title: str, number: int, segment: Optional[int]):
        self.kind = kind
        self.title = title
        self.number = number
        self.segment = segment
        self.lines: list[str] = []

    @property
    def text(self) -> str:
        return " ".join(self.lines)

    @property
    def words(self) -> list[str]:
        return self.text.split()


def parse_units(script_path: Path) -> list[Unit]:
    units: list[Unit] = []
    cur: Optional[Unit] = None
    segment: Optional[int] = None

    def start(u: Unit) -> None:
        nonlocal cur
        cur = u
        units.append(u)

    for raw in script_path.read_text(encoding="utf-8").splitlines():
        m = STORY_RE.match(raw)
        if m:
            n, title = int(m.group(1)), m.group(2).strip()
            start(Unit("story", title, n, segment))
            continue
        m = H2_RE.match(raw)
        if m:
            h = _clean_heading(m.group(1))
            glyph = next((g for g in SEGMENT_GLYPHS if g in h), None)
            if glyph:
                segment = SEGMENT_GLYPHS[glyph]
                cur = None  # segment preamble is not a unit
                continue
            hl = h.lower()
            if hl == "intro":
                start(Unit("intro", "Intro", 0, None))
            elif hl.startswith("the close (final)"):
                start(Unit("close", "The Close", 99, None))
            elif hl == "cta":
                start(Unit("cta", "CTA", 98, None))
            else:
                cur = None  # "the close (draft)" and anything else: not spoken here
            continue
        if raw.startswith("#"):
            cur = None
            continue
        if cur is None:
            continue
        s = _spoken(raw)
        if s:
            cur.lines.append(s)

    return units


def check_units(units: list[Unit]) -> list[str]:
    problems = []
    stories = [u for u in units if u.kind == "story"]
    nums = [u.number for u in stories]
    if nums != list(range(1, 39)):
        problems.append(f"expected stories 1..38 in order, got {nums}")
    for kind in ("intro", "close", "cta"):
        if not any(u.kind == kind for u in units):
            problems.append(f"missing unit kind={kind!r}")
    for u in units:
        if not u.lines:
            problems.append(f"unit {u.kind} {u.number} ({u.title!r}) has no spoken lines")
    return problems


# --- word-timing synthesis (deterministic) --------------------------------------------

def synthesize_words(units: list[Unit]) -> list[Word]:
    """Lay every unit's words end to end at `WORDS_PER_SECOND`, with a pause before each new
    unit -- `SECTION_PAUSE` when the unit starts what used to be a top-level section (Intro /
    a numbered segment's first story / Close), `STORY_PAUSE` between stories within the same
    segment (and before CTA, folded on as a trailing beat after Close). Neither pause is a
    heading any more (T24): they only give the web layer's pause-based paragraphing (>= 1.5s)
    something real to key off, matching how an actual take would breathe between beats."""
    words: list[Word] = []
    t = 0.0
    prev_kind: Optional[str] = None
    prev_segment: Optional[int] = None

    for unit in units:
        if prev_kind is not None:
            is_new_top_level = (
                unit.kind in ("intro", "close")
                or (unit.kind == "story" and unit.segment != prev_segment)
            )
            t += SECTION_PAUSE if is_new_top_level else STORY_PAUSE

        for token in unit.words:
            words.append(Word(text=token, start=round(t, 6), end=round(t + WORD_DURATION, 6)))
            t += WORD_DURATION

        prev_kind = unit.kind
        if unit.kind == "story":
            prev_segment = unit.segment

    return words


# --- project build ---------------------------------------------------------------------

def build(force: bool) -> None:
    if not SCRIPT_PATH.is_file():
        sys.exit(f"read-only input missing: {SCRIPT_PATH}")

    if PROJECT_ROOT.is_dir():
        if not force:
            print(f"{PROJECT_ROOT} already exists; reusing it (pass --force to rebuild)")
            return
        import shutil

        shutil.rmtree(PROJECT_ROOT)

    units = parse_units(SCRIPT_PATH)
    problems = check_units(units)
    if problems:
        sys.exit("script parse problems:\n" + "\n".join(f"  - {p}" for p in problems))

    words = synthesize_words(units)
    total_word_count = sum(len(u.words) for u in units)
    if len(words) != total_word_count:
        sys.exit(f"internal error: {len(words)} synthesised words != {total_word_count} parsed words")

    fps = Rational(num=25, den=1)
    fingerprint = "virtual:" + hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()[:16]

    store_module.init_project(PROJECT_ROOT)
    project = Project(name=PROJECT_NAME, root=str(PROJECT_ROOT))
    store_module.write(PROJECT_ROOT, "project", project, expected_rev=0)

    source = Source(
        path=None, kind="virtual", fps=fps, role="a_roll", content_fingerprint=fingerprint,
    )
    sync_group = SyncGroup(source_ids=[source.id], offsets={source.id: 0.0})
    shoot = Shoot(name="locked-cut (virtual)", sources=[source], sync_groups=[sync_group])
    store_module.write(PROJECT_ROOT, "shoot", shoot, expected_rev=0)

    transcript = Transcript(
        sync_group_id=sync_group.id, provider="script:mega-cut", words=words, fingerprint=fingerprint,
    )
    store_module.write(PROJECT_ROOT, "transcript", transcript, expected_rev=0)
    shoot = shoot.model_copy(update={"transcript_ids": [transcript.id]})
    store_module.write(PROJECT_ROOT, "shoot", shoot, expected_rev=1)

    # T24: ONE passage over every word, in document order -- a raw, continuous transcript,
    # no Sections. This is what makes it read like a real single-take Deepgram transcript
    # rather than an assembled, chaptered script.
    passages: list[Passage] = []
    if words:
        passages.append(Passage(
            sync_group_id=sync_group.id, start_word_id=words[0].id, end_word_id=words[-1].id,
            angle_source_id=source.id,
        ))

    cut = Cut(aspect=Rational(num=16, den=9), fps=fps, sections=[], passages=passages)
    store_module.write(PROJECT_ROOT, "cut", cut, expected_rev=0)

    print(f"project: {PROJECT_ROOT}")
    print(f"cut: {cut.id}")
    print(f"words: {len(words)}  passages: {len(passages)}  sections: 0 (raw transcript, T24)")
    print(f"duration: {words[-1].end:.1f}s" if words else "duration: 0.0s")

    meta = {"project_root": str(PROJECT_ROOT), "cut_id": cut.id, "name": PROJECT_NAME}
    (PROJECT_ROOT / "meta.json").write_text(__import__("json").dumps(meta, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="wipe and rebuild .demo-script/ even if it already exists")
    args = ap.parse_args()
    build(args.force)


if __name__ == "__main__":
    main()
