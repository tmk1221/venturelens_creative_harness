"""`asset.verify`: probe a produced still/video with ffprobe (resolution/fps/duration; local,
offline, never paid) -- plus, for generated video, T37's render contract (`recipes.
render_contract`: video stream, project fps, span length, frozen tail, aspect; each failure
one sentence, joined into the result detail the card shows) -- and, if it passes, register it as an `Asset` (T12 carry-over) naming
the *downstream* `human.approve` node's id/hash -- not this node's own -- so
`graph.approvals.is_approved(asset.content_hash)` (what `export._context.asset_done_and_
approved` checks) lines up with the hash a human's `graph.approvals.approve()` call actually
names (the approve node's own `input_hash`, per `graph.state.compute_states`). `cmd_for`
computes that node id/hash and passes them in as `--record-as-node`/`--record-as-hash`.

A worker that fails its own probe exits 1 (T03 contract) instead of writing an Asset at
all -- there is no "verified but not approvable" state.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ... import store as store_mod
from ...model.asset import Asset
from ...model.common import Rational
from ...workers.contract import emit
from .. import render_contract
from ._common import add_common_args, fake_mode, probe_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--media", required=True)
    parser.add_argument("--expect-kind", default="video", choices=["video", "image"])
    parser.add_argument("--min-width", type=int, default=0)
    parser.add_argument("--min-height", type=int, default=0)
    parser.add_argument("--record-as-node", required=True)
    parser.add_argument("--record-as-hash", required=True)
    parser.add_argument("--role", default="picture")
    parser.add_argument("--expect-fps", default=None)
    parser.add_argument("--min-seconds", type=float, default=None)
    parser.add_argument("--expect-aspect", default=None)
    parser.add_argument("--reject-frozen-tail", action="store_true")
    args = parser.parse_args(argv)

    media_path = Path(args.media).resolve()
    if not media_path.is_file():
        emit("result", ok=False, detail=f"asset.verify: {media_path} does not exist")
        return 1

    problems = _contract_problems(media_path, args) if args.expect_kind == "video" else []
    if problems[:1] == ["The file has no video stream."]:
        return _fail(Path("verify.json"), media_path, problems, {})
    probe = probe_video(media_path)
    if args.expect_kind == "video" and not probe.get("duration_frames"):
        problems.append("no frame count probed")
    width, height = probe.get("width") or 0, probe.get("height") or 0
    if width < args.min_width:
        problems.append(f"width {width} < required {args.min_width}")
    if height < args.min_height:
        problems.append(f"height {height} < required {args.min_height}")

    verify_path = Path("verify.json")
    if problems:
        return _fail(verify_path, media_path, problems, probe)
    _write_verify(verify_path, media_path, problems, probe)

    fps = Rational(num=probe["fps_num"], den=probe["fps_den"]) if args.expect_kind == "video" else None
    asset = Asset(
        id=args.record_as_hash,
        role=args.role,
        node_id=args.record_as_node,
        content_hash=args.record_as_hash,
        path=str(media_path),
        fps=fps,
        duration_frames=probe.get("duration_frames"),
    )
    _existing, rev = store_mod.try_read(args.project_root, "asset", asset.id)
    store_mod.write(args.project_root, "asset", asset, expected_rev=rev)

    import hashlib

    sha = hashlib.sha256(verify_path.read_bytes()).hexdigest()
    emit("artifact", path=str(verify_path), role="verify", sha256=sha)
    emit("result", ok=True, detail="verified")
    return 0


def _contract_problems(media_path: Path, args) -> list[str]:
    media = render_contract.probe(media_path)
    frozen = 0.0
    if media.has_video and args.reject_frozen_tail and media.seconds:
        frozen = render_contract.frozen_tail_seconds(media_path, media.seconds)
    return render_contract.check(
        media, expect_fps=args.expect_fps, min_seconds=args.min_seconds,
        expect_aspect=args.expect_aspect, frozen_tail=frozen,
    )


def _write_verify(verify_path: Path, media_path: Path, problems: list[str], probe: dict) -> None:
    verify_path.write_text(
        json.dumps({"ok": not problems, "problems": problems, "probe": probe, "media": str(media_path)}, indent=2),
        encoding="utf-8",
    )


def _fail(verify_path: Path, media_path: Path, problems: list[str], probe: dict) -> int:
    """T37: the detail is the problems themselves, each already a sentence -- the executor
    files it as the node's failure summary, which is what the card shows."""
    _write_verify(verify_path, media_path, problems, probe)
    emit("artifact", path=str(verify_path), role="verify", sha256=None)
    emit("result", ok=False, detail=" ".join(p if p.endswith(".") else f"asset.verify: {p}." for p in problems))
    return 1


if __name__ == "__main__":
    sys.exit(main())
