"""`still.generate`: one image variant from a prompt, plus optional continuity references.

Both modes estimate first and refuse (exit 2) without one (`_spend.py`, T31). Fake mode
(every test) synthesises a placeholder PNG with ffmpeg -- no call to Higgsfield. Real mode
uploads any local continuity images, then `higgsfield generate create nano_banana_2 ...`
(see `higgsfield_cli.py` for the exact, partly-unverified shape), recording the cost the
moment the paid call returns.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ...workers.contract import emit
from .. import models
from . import higgsfield_cli
from ._common import add_common_args, emit_artifact_ok, fake_mode, placeholder_image, placeholder_size
from ._spend import EXIT_USAGE, cost_event, estimate_or_refuse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--model", default="nano_banana_2")
    parser.add_argument("--aspect", default="16:9")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--continuity", action="append", default=[])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--variant-index", type=int, default=0)
    parser.add_argument("--out", default="image.png")
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    emit("prompt", text=args.prompt, model=args.model)
    estimate = estimate_or_refuse("still.generate", args.model, lambda: models.estimate_still(args.model, args.aspect))
    if estimate is None:
        return EXIT_USAGE

    if fake_mode():
        placeholder_image(out_path, label=f"still:{args.node_id}:v{args.variant_index}", size=placeholder_size(args.aspect))
        emit_artifact_ok(out_path, role="image", cost=cost_event(estimate))
        return 0
    try:
        image_ids = [higgsfield_cli.upload_image(Path(p)) for p in args.continuity]
        cli_args = ["--prompt", args.prompt, "--aspect_ratio", args.aspect, "--resolution", "2k"]
        for iid in image_ids:
            cli_args += ["--image", iid]
        job = higgsfield_cli.generate(args.model, cli_args)
        emit("cost", **cost_event(estimate, higgsfield_cli.reported_cost(job)))
        higgsfield_cli.download(job, out_path)
    except Exception as exc:  # noqa: BLE001 -- any failure here is a worker failure
        emit("result", ok=False, detail=f"still.generate failed: {exc}")
        return 1
    emit_artifact_ok(out_path, role="image")
    return 0

if __name__ == "__main__":
    sys.exit(main())
