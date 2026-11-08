#!/usr/bin/env python3
"""Build a small demo project under `.demo/` so Travis can click around the web editor
without touching real footage, the network, or any paid provider (AGENTS.md: no real
footage, no network, no paid calls -- T19).

Everything comes from `ffmpeg lavfi` (a synthetic audio tone) and a generated word list
imported as a transcript through the same `post` CLI a real ingest would use. Idempotent:
re-running reuses an existing `.demo/project` unless `--force` wipes it first.

T22: Post plays audio only -- the source clip still carries a (throwaway) picture track so
the demo looks like a real a_roll source, but ingest here only ever builds the audio proxy
+ peaks the editor actually uses, never a video proxy.

Usage (also wired as `make demo-project`):
    packages/post_core/.venv/bin/python scripts/make_demo_project.py [--force]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / ".demo"
PROJECT_ROOT = DEMO_DIR / "project"
MEDIA_DIR = DEMO_DIR / "media"
POST_BIN = REPO_ROOT / "packages" / "post_core" / ".venv" / "bin" / "post"

# A talking-head-shaped word list (no real transcript, no network) long enough to show off
# passages, "remove fillers" suggestions, and a plausible "derive short" selection.
_SCRIPT = (
    "so um today we're going to talk about the launch basically it's been a long few weeks "
    "but the team pulled it together and honestly i think people are going to like what we "
    "shipped the biggest change is speed uh everything just feels faster now and second the "
    "new onboarding flow cuts the time to first value from like ten minutes down to about "
    "ninety seconds which you know doesn't sound like much until you watch someone actually "
    "use it we also fixed the sync bug that was dropping edits under load that one had been "
    "open forever so it feels really good to finally close it out next quarter we're focused "
    "on the mobile app and a few requests from bigger customers around permissions and audit "
    "logs anyway that's the update thanks for watching and we'll see you next time"
).split()


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def post(*args: str) -> dict:
    proc = sh([str(POST_BIN), *args])
    return json.loads(proc.stdout)


def make_clip(out: Path, duration: float) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"color=c=0x3a5a8c:s=640x360:r=25:d={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=220:duration={duration}",
            "-vf", "drawtext=text='Post v3 demo — %{pts\\:hms}':x=20:y=20:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5",
            "-shortest", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
            str(out),
        ],
        check=True, capture_output=True,
    )


def build(force: bool) -> None:
    if not POST_BIN.is_file():
        sys.exit(f"post CLI not found at {POST_BIN} -- build packages/post_core/.venv first (see docs/HANDOFF.md)")

    if PROJECT_ROOT.is_dir():
        if not force:
            print(f"{PROJECT_ROOT} already exists; reusing it (pass --force to rebuild)")
            return
        shutil.rmtree(DEMO_DIR)

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_ROOT.mkdir(parents=True)

    word_dur = 0.32
    duration = len(_SCRIPT) * word_dur + 1.0
    clip = MEDIA_DIR / "interview.mp4"
    print(f"generating {duration:.1f}s lavfi clip -> {clip}")
    make_clip(clip, duration)

    print("post init")
    post("init", str(PROJECT_ROOT), "--name", "Demo")

    print("post source add")
    src = post("source", "add", "--root", str(PROJECT_ROOT), "--path", str(clip), "--role", "a_roll")
    shoot_id, source_id, sync_group_id = src["shoot_id"], src["source_id"], src["sync_group_id"]

    print("post ingest audio + peaks")
    post("ingest", "audio", "--root", str(PROJECT_ROOT), "--shoot", shoot_id, "--source-id", source_id)
    post("ingest", "peaks", "--root", str(PROJECT_ROOT), "--shoot", shoot_id, "--source-id", source_id)

    print("post ingest import-transcript")
    words = [{"text": w, "start": i * word_dur, "end": i * word_dur + word_dur * 0.8} for i, w in enumerate(_SCRIPT)]
    transcript_path = DEMO_DIR / "transcript.json"
    transcript_path.write_text(json.dumps(words))
    imp = post(
        "ingest", "import-transcript", "--root", str(PROJECT_ROOT),
        "--shoot", shoot_id, "--sync-group", sync_group_id, "--path", str(transcript_path), "--format", "json",
    )
    transcript_id = imp["transcript_id"]

    print("post cut new")
    cut = post(
        "cut", "new", "--root", str(PROJECT_ROOT),
        "--transcript", transcript_id, "--angle", source_id, "--aspect", "16:9",
    )
    cut_id = cut["cut_id"]

    # Registration with post_api (which assigns the routable project id, independent of the
    # on-disk Project's own id) happens at server startup in scripts/dev.sh, via a real
    # `POST /api/projects` call -- not hand-written here -- so the registry entry is byte-for-
    # byte what the production flow would produce.
    meta = {"project_root": str(PROJECT_ROOT), "cut_id": cut_id, "name": "Demo"}
    (DEMO_DIR / "meta.json").write_text(json.dumps(meta, indent=2))

    print(f"\ndemo project ready: {PROJECT_ROOT}")
    print(f"cut id: {cut_id}")
    print(f"meta: {DEMO_DIR / 'meta.json'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="wipe and rebuild .demo/ even if it already exists")
    args = ap.parse_args()
    build(args.force)


if __name__ == "__main__":
    main()
