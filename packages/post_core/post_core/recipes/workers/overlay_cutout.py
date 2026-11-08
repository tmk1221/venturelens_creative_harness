"""`overlay.cutout` (optional, T12 spec): background removal on an overlay candidate.

NOT WIRED to a real matting/background-removal tool -- none is specified anywhere T12 reads
from (SKILL.md/audit/ARCHITECTURE.md), and this repo forbids guessing at a paid provider's
CLI. Fake mode (and, for now, real mode too) re-encodes the input through ffmpeg unchanged
as a structurally valid placeholder so the rest of the graph (`asset.verify`, export) can be
exercised end to end; a human should replace the body of `_cutout` with a real call before
this node type is used for a real overlay.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ._common import add_common_args, emit_artifact_ok


def _cutout(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), str(dest)], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", default="output.mp4")
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    _cutout(Path(args.video), out_path)
    emit_artifact_ok(out_path, role="video")
    return 0


if __name__ == "__main__":
    sys.exit(main())
