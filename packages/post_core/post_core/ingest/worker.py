"""`python -m post_core.ingest.worker proxy|peaks|transcribe ...`

Each subcommand speaks the T03 ``##POST`` contract (post_core.workers.contract): emits
`step`/`artifact`/`result` events and exits with the codes `runner.run` understands, so
these can be driven by `runner.run`/`legacy` exactly like any other worker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from post_core.workers import contract

from . import audio_proxy as audio_proxy_mod
from . import peaks as peaks_mod
from . import proxy as proxy_mod
from .transcribe import base as transcribe_base
from .transcribe import importer


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _emit_artifact(path: Path, role: str) -> None:
    contract.emit("artifact", path=str(path), role=role, sha256=_sha256(path))


def _fail(exc: Exception) -> int:
    contract.emit("err", text=str(exc))
    contract.emit("result", ok=False, detail=str(exc))
    return contract.EXIT_FAILED


def run_proxy(args: argparse.Namespace) -> int:
    contract.emit("step", label="building proxy")
    try:
        out = proxy_mod.build_proxy(args.source, args.out_dir, args.fingerprint,
                                     height=args.height, force=args.force)
    except Exception as exc:  # noqa: BLE001 - reported through the contract, not raised
        return _fail(exc)
    _emit_artifact(out, "proxy")
    contract.emit("result", ok=True, detail=str(out))
    return contract.EXIT_OK


def run_audio(args: argparse.Namespace) -> int:
    contract.emit("step", label="building audio proxy")
    try:
        out = audio_proxy_mod.build_audio_proxy(args.source, args.out_dir, args.fingerprint, force=args.force)
    except Exception as exc:  # noqa: BLE001 - reported through the contract, not raised
        return _fail(exc)
    _emit_artifact(out, "audio_proxy")
    contract.emit("result", ok=True, detail=str(out))
    return contract.EXIT_OK


def run_peaks(args: argparse.Namespace) -> int:
    contract.emit("step", label="building peaks")
    try:
        out = peaks_mod.build_peaks(args.source, args.out, samples_per_sec=args.rate)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)
    _emit_artifact(out, "peaks")
    contract.emit("result", ok=True, detail=str(out))
    return contract.EXIT_OK


def run_transcribe(args: argparse.Namespace) -> int:
    contract.emit("step", label=f"transcribing via {args.provider}")
    try:
        if args.provider == "import":
            text = Path(args.source).read_text()
            fmt = args.format or importer.guess_format(args.source)
            words = importer.import_words(text, fmt)
            transcript = importer.words_to_transcript(
                words, sync_group_id=args.sync_group_id,
                provider=f"import:{fmt}", fingerprint=args.fingerprint)
        else:
            provider = transcribe_base.get(args.provider)
            opts = json.loads(args.opts) if args.opts else {}
            opts.setdefault("sync_group_id", args.sync_group_id)
            opts.setdefault("fingerprint", args.fingerprint)
            transcript = provider.transcribe(args.source, opts)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(transcript.model_dump_json())
    tmp.replace(out_path)

    _emit_artifact(out_path, "transcript")
    contract.emit("result", ok=True, detail=str(out_path))
    return contract.EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m post_core.ingest.worker")
    sub = ap.add_subparsers(dest="job", required=True)

    p = sub.add_parser("proxy")
    p.add_argument("--source", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--fingerprint", required=True)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=run_proxy)

    p = sub.add_parser("audio")
    p.add_argument("--source", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--fingerprint", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=run_audio)

    p = sub.add_parser("peaks")
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--rate", type=int, default=100)
    p.set_defaults(func=run_peaks)

    p = sub.add_parser("transcribe")
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--provider", required=True, help="'deepgram', 'local', or 'import'")
    p.add_argument("--sync-group-id", dest="sync_group_id", required=True)
    p.add_argument("--fingerprint", required=True)
    p.add_argument("--format", default=None, help="for --provider import: json|srt|vtt")
    p.add_argument("--opts", default=None, help="JSON dict of provider-specific options")
    p.set_defaults(func=run_transcribe)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
