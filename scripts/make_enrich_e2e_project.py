#!/usr/bin/env python3
"""Build the tiny on-disk project the T26 Playwright acceptance test drives: a
post-picture-lock "raw transcript" project (T24 shape -- a single `kind="virtual"` Source,
no real media at all, one continuous Passage) so the web app's raw-transcript workspace
(`RawTranscript`/`VisualsRail`) is what actually mounts -- the T26 card/graph views only
render there. Self-contained (unlike `make_acme_script_demo.py`, this reads no file
outside this repo): a handful of hand-written words, built directly through
`post_core.store`, same primitives that script uses. Lives under its own `.demo-enrich-e2e/`
dir so it never collides with `make dev`'s `.demo/`. No network, no real footage, no paid
provider (AGENTS.md/T26); the caller sets `POST3_FAKE_PROVIDERS=1` on the post_api process
that actually serves this project.

Usage: packages/post_core/.venv/bin/python scripts/make_enrich_e2e_project.py [--force]
Writes `.demo-enrich-e2e/meta.json`: {"project_root", "cut_id"}.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages" / "post_core"))

from post_core.model.common import Rational  # noqa: E402
from post_core.model.cut import Cut, Passage  # noqa: E402
from post_core.model.project import Project  # noqa: E402
from post_core.model.shoot import Shoot, Source, SyncGroup  # noqa: E402
from post_core.model.transcript import Transcript, Word  # noqa: E402
from post_core.store import store as store_module  # noqa: E402

DEMO_DIR = REPO_ROOT / ".demo-enrich-e2e"
PROJECT_ROOT = DEMO_DIR / "project"
PROJECT_NAME = "T26 enrich e2e"

WORDS_PER_SECOND = 2.6
WORD_DURATION = 1.0 / WORDS_PER_SECOND

# T30d: extended from the original 15 words to 20 so `enrich_e2e_up.sh` has room to carve out
# five non-overlapping word ranges on the one passage -- one per recipe kind the T30d graph
# nodes need exercised (video/anim/provided/overlay), plus a spare couple of words left
# unclaimed for the live "select words -> Add visual -> Open in graph" dialog flow (the
# focusNodeId acceptance check) -- see that script's own comment for the exact split.
_SCRIPT = "so today we are going to talk about the launch and what shipped this week we also want to show".split()


def build(force: bool) -> dict:
    if PROJECT_ROOT.is_dir():
        if not force:
            meta = json.loads((DEMO_DIR / "meta.json").read_text())
            print(f"{PROJECT_ROOT} already exists; reusing it (pass --force to rebuild)")
            return meta
        shutil.rmtree(DEMO_DIR)

    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    words: list[Word] = []
    t = 0.0
    for token in _SCRIPT:
        words.append(Word(text=token, start=round(t, 6), end=round(t + WORD_DURATION, 6)))
        t += WORD_DURATION

    fps = Rational(num=25, den=1)
    fingerprint = "virtual:" + hashlib.sha256(" ".join(_SCRIPT).encode()).hexdigest()[:16]

    print("post_core.store.init_project")
    store_module.init_project(PROJECT_ROOT)
    project = Project(name=PROJECT_NAME, root=str(PROJECT_ROOT))
    store_module.write(PROJECT_ROOT, "project", project, expected_rev=0)

    source = Source(path=None, kind="virtual", fps=fps, role="a_roll", content_fingerprint=fingerprint)
    sync_group = SyncGroup(source_ids=[source.id], offsets={source.id: 0.0})
    shoot = Shoot(name="locked-cut (virtual)", sources=[source], sync_groups=[sync_group])
    store_module.write(PROJECT_ROOT, "shoot", shoot, expected_rev=0)

    transcript = Transcript(
        sync_group_id=sync_group.id, provider="enrich-e2e:script", words=words, fingerprint=fingerprint,
    )
    store_module.write(PROJECT_ROOT, "transcript", transcript, expected_rev=0)
    shoot = shoot.model_copy(update={"transcript_ids": [transcript.id]})
    store_module.write(PROJECT_ROOT, "shoot", shoot, expected_rev=1)

    passages = [Passage(
        sync_group_id=sync_group.id, start_word_id=words[0].id, end_word_id=words[-1].id,
        angle_source_id=source.id,
    )]
    cut = Cut(aspect=Rational(num=16, den=9), fps=fps, sections=[], passages=passages)
    store_module.write(PROJECT_ROOT, "cut", cut, expected_rev=0)

    # T30d: `word_ids` (ordered, one per `_SCRIPT` token) lets `enrich_e2e_up.sh` slice out
    # several non-overlapping word ranges by plain index instead of re-deriving them from the
    # API -- see that script for which index range feeds which recipe kind.
    meta = {
        "project_root": str(PROJECT_ROOT), "cut_id": cut.id, "sync_group_id": sync_group.id,
        "word_ids": [w.id for w in words],
    }
    (DEMO_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\ne2e project ready: {PROJECT_ROOT}\ncut id: {cut.id}\nwords: {len(words)}")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    build(args.force)


if __name__ == "__main__":
    main()
