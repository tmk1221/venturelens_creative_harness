"""`video.generate`: a video from a start image (+ optional end image) and a motion prompt.
`--duration` is the caller's already-computed `ceil(span seconds) + 1` (instantiate.py) --
this worker does not touch span/timeline math, only generates and probes.

Fake mode synthesises a placeholder MP4 with ffmpeg at the requested duration and probes it
with ffprobe (real, local, offline) so `fps_num`/`fps_den`/`duration_frames` land on the
artifact event -- exercising the same T12 carry-over path (`Asset.fps`/`duration_frames`)
a real Higgsfield download would need. Real mode calls `higgsfield generate create kling3_0
...` (see `higgsfield_cli.py`).

T37: `--aspect` is what the model is asked for; `--crop-to` (the cut's aspect, when the model
doesn't offer it) centre-crops the result locally into `video.mp4`, keeping the uncropped
`generated.mp4` as a second artifact (it was paid for). `--fps` is the project's rate, used
only by the fake placeholder -- a real provider picks its own and `asset.verify` checks it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ... import aspect as aspect_mod
from ...workers.contract import emit
from .. import models
from . import higgsfield_cli
from ._common import (
    add_common_args, crop_video_to_aspect, emit_artifact_ok, fake_mode, placeholder_size,
    placeholder_video, probe_video,
)
from ._spend import EXIT_USAGE, cost_event, estimate_or_refuse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--model", default="kling3_0")
    parser.add_argument("--aspect", default="16:9")
    parser.add_argument("--mode", default="pro")
    parser.add_argument("--sound", action="store_true")
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("--motion-prompt", required=True)
    parser.add_argument("--start-image", required=True)
    parser.add_argument("--end-image", default=None)
    parser.add_argument("--out", default="video.mp4")
    parser.add_argument("--crop-to", default=None)
    parser.add_argument("--fps", default=None)
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    cropping = bool(args.crop_to) and not aspect_mod.same(args.crop_to, args.aspect)
    gen_path = out_path.with_name("generated.mp4") if cropping else out_path
    emit("prompt", text=args.motion_prompt, model=args.model)
    estimate = estimate_or_refuse(
        "video.generate", args.model, lambda: models.estimate_video(args.model, args.duration, args.mode),
    )
    if estimate is None:
        return EXIT_USAGE

    cost = None
    if fake_mode():
        placeholder_video(
            gen_path, label=f"video:{args.node_id}", seconds=float(args.duration),
            fps=args.fps or 24, size=placeholder_size(args.aspect),
        )
        cost = cost_event(estimate)
    else:
        try:
            image_ids = [higgsfield_cli.upload_image(Path(args.start_image))]
            if args.end_image:
                image_ids.append(higgsfield_cli.upload_image(Path(args.end_image)))
            cli_args = [
                "--prompt", args.motion_prompt, "--aspect_ratio", args.aspect,
                "--duration", str(args.duration), "--mode", args.mode,
            ]
            for iid in image_ids:
                cli_args += ["--start-image", iid]
            job = higgsfield_cli.generate(args.model, cli_args)
            emit("cost", **cost_event(estimate, higgsfield_cli.reported_cost(job)))
            higgsfield_cli.download(job, gen_path)
        except Exception as exc:  # noqa: BLE001
            emit("result", ok=False, detail=f"video.generate failed: {exc}")
            return 1

    extra: dict = {}
    also: list[tuple[Path, str]] = []
    if cropping:
        try:
            crop_video_to_aspect(gen_path, out_path, args.crop_to)
        except Exception as exc:  # noqa: BLE001
            emit("result", ok=False, detail=f"video.generate could not crop to {args.crop_to}: {exc}")
            return 1
        extra = {"generated_aspect": aspect_mod.label(args.aspect), "crop_to": aspect_mod.label(args.crop_to)}
        also = [(gen_path, "generated")]
    probe = probe_video(out_path)
    emit_artifact_ok(out_path, role="video", cost=cost, also=also, **probe, **extra)
    return 0

if __name__ == "__main__":
    sys.exit(main())
