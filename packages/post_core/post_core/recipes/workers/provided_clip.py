"""`provided.clip`: register already-ingested footage as a workflow asset without moving,
copying, or otherwise touching it (AGENTS.md: never mutate live footage/Resolve). Probes it
read-only with ffprobe, writes a small local pointer file as its own artifact (so the T04
state machine can mark this node `done`), and writes the `Asset` record itself -- same
`--record-as-node`/`--record-as-hash` convention as `asset_verify.py` (this node has no
separate `asset.verify` step downstream; see `recipes/instantiate.py`'s `provided` recipe).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from ... import store as store_mod
from ...model.asset import Asset
from ...model.common import Rational
from ...workers.contract import emit
from ._common import add_common_args, probe_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--path", required=True)
    parser.add_argument("--in-seconds", type=float, default=0.0)
    parser.add_argument("--out-seconds", type=float, default=None)
    parser.add_argument("--record-as-node", required=True)
    parser.add_argument("--record-as-hash", required=True)
    parser.add_argument("--role", default="picture")
    args = parser.parse_args(argv)

    source_path = Path(args.path).resolve()
    if not source_path.is_file():
        emit("result", ok=False, detail=f"provided.clip: {source_path} does not exist")
        return 1

    probe = probe_video(source_path)
    pointer_path = Path("pointer.json")
    pointer_path.write_text(
        json.dumps({"path": str(source_path), "in_seconds": args.in_seconds,
                     "out_seconds": args.out_seconds, "probe": probe}, indent=2),
        encoding="utf-8",
    )

    fps = Rational(num=probe["fps_num"], den=probe["fps_den"]) if probe.get("fps_num") else None
    asset = Asset(
        id=args.record_as_hash,
        role=args.role,
        node_id=args.record_as_node,
        content_hash=args.record_as_hash,
        path=str(source_path),
        fps=fps,
        duration_frames=probe.get("duration_frames"),
    )
    _existing, rev = store_mod.try_read(args.project_root, "asset", asset.id)
    store_mod.write(args.project_root, "asset", asset, expected_rev=rev)

    sha = hashlib.sha256(pointer_path.read_bytes()).hexdigest()
    emit("artifact", path=str(pointer_path), role="pointer", sha256=sha)
    emit("result", ok=True, detail="registered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
