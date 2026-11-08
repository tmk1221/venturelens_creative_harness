"""`animation.draft_render`: a fast/low-res HyperFrames render for human review before the
final `animation.render`. Fake mode: an ffmpeg placeholder (local, offline). Real mode:
`hyperframes_cli.render` (see that module for the one unverified CLI-shape assumption)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ...workers.contract import emit
from . import hyperframes_cli
from ._common import add_common_args, emit_artifact_ok, fake_mode, placeholder_video, probe_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--composition-dir", required=True)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--out", default="draft.mp4")
    args = parser.parse_args(argv)

    comp_dir = Path(args.composition_dir)
    if not (comp_dir / "index.html").is_file():
        emit("result", ok=False, detail=f"animation.draft_render: no index.html in {comp_dir}")
        return 1

    out_path = Path(args.out)
    if fake_mode():
        placeholder_video(out_path, label=f"draft:{args.node_id}", seconds=2.0, fps=args.fps,
                           size=f"{args.width}x{args.height}")
    else:
        try:
            hyperframes_cli.render(comp_dir, out_path, args.width, args.height, args.fps)
        except Exception as exc:  # noqa: BLE001
            emit("result", ok=False, detail=f"animation.draft_render failed: {exc}")
            return 1

    probe = probe_video(out_path)
    emit_artifact_ok(out_path, role="video", **probe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
