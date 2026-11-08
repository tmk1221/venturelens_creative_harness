"""`aroll.regenerate` (T15 stub, T30b spec line): records the regen request -- mode +
instruction -- as its artifact. No presenter voice/likeness generation happens here; T15
owns the real providers (TTS/lipsync/twin) once that task is built. Fake mode only, same as
every other worker in this package; real mode fails loudly rather than doing nothing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ...workers.contract import emit
from ._common import add_common_args, emit_artifact_ok, fake_mode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--mode", required=True, choices=["fix_line", "alternate_opening", "synthetic_segment"])
    parser.add_argument("--instruction", default="")
    parser.add_argument("--out", default="request.json")
    args = parser.parse_args(argv)

    if not fake_mode():
        emit(
            "result", ok=False,
            detail="aroll.regenerate: real-mode providers are not wired yet (T15); run under "
                   "POST3_FAKE_PROVIDERS=1 for now.",
        )
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"mode": args.mode, "instruction": args.instruction}, indent=2), encoding="utf-8",
    )

    emit_artifact_ok(out_path, role="text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
