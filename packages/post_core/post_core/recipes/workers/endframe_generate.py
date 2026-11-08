"""`endframe.generate` (optional per T12 spec): one end frame conditioned on the start
frame + a prompt. Same shape as `still.generate`, kept as its own worker because its node
type has its own inputs/params (a `frame` to condition on, not `continuity` references)."""
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
    parser.add_argument("--frame", required=True)
    parser.add_argument("--out", default="endframe.png")
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    emit("prompt", text=args.prompt, model=args.model)
    estimate = estimate_or_refuse("endframe.generate", args.model, lambda: models.estimate_still(args.model, args.aspect))
    if estimate is None:
        return EXIT_USAGE

    if fake_mode():
        placeholder_image(out_path, label=f"endframe:{args.node_id}", size=placeholder_size(args.aspect))
        emit_artifact_ok(out_path, role="image", cost=cost_event(estimate))
        return 0
    try:
        frame_id = higgsfield_cli.upload_image(Path(args.frame))
        cli_args = [
            "--prompt", args.prompt, "--aspect_ratio", args.aspect,
            "--resolution", "2k", "--image", frame_id,
        ]
        job = higgsfield_cli.generate(args.model, cli_args)
        emit("cost", **cost_event(estimate, higgsfield_cli.reported_cost(job)))
        higgsfield_cli.download(job, out_path)
    except Exception as exc:  # noqa: BLE001
        emit("result", ok=False, detail=f"endframe.generate failed: {exc}")
        return 1
    emit_artifact_ok(out_path, role="image")
    return 0

if __name__ == "__main__":
    sys.exit(main())
