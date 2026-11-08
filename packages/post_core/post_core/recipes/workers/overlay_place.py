"""`overlay.place`: tags an already-produced overlay candidate with depth/position (T30b).
No media transform -- the params alone (depth/position) carry the placement decision, so
this worker's whole job is to make the input video its own output (a copy, not a re-encode:
the file is already a valid video, fake mode or real) at a path this node type owns, so
downstream nodes (`asset.verify`, `human.approve`) hash off *this* node rather than reaching
back through the conditional measure/cutout branch."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from ._common import add_common_args, emit_artifact_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--video", required=True)
    parser.add_argument("--depth", required=True, choices=["in_front", "behind"])
    parser.add_argument("--position", required=True)
    parser.add_argument("--out", default="output.mp4")
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.video, out_path)

    emit_artifact_ok(out_path, role="overlay", depth=args.depth, position=args.position)
    return 0


if __name__ == "__main__":
    sys.exit(main())
