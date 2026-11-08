"""`overlay.measure` (optional, T12 spec): probe an overlay candidate's own dimensions so a
placement step can size it against the kit's safe areas. Local ffprobe only, no provider
call in either mode -- there's nothing to fake."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from ...workers.contract import emit
from ._common import add_common_args, probe_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--video", required=True)
    parser.add_argument("--out", default="measurements.json")
    args = parser.parse_args(argv)

    probe = probe_video(Path(args.video))
    out_path = Path(args.out)
    out_path.write_text(json.dumps(probe, indent=2), encoding="utf-8")

    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    emit("artifact", path=str(out_path), role="measurements", sha256=sha)
    emit("result", ok=True, detail="measured")
    return 0


if __name__ == "__main__":
    sys.exit(main())
