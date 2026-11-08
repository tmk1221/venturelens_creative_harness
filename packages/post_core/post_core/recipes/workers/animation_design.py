"""`animation.design`: build a HyperFrames composition scaffold (index.html + brand.css +
the kit's `animation_brief` JSON) and brand-lint it (`brandkit.lint.lint_composition`) --
T12 spec: "brand lint runs as part of design's check and can fail". The lint runs here, at
worker time, and a violation makes the *worker* fail (exit 1, `result{ok:false}`) rather
than merely leaving `check()` unsatisfied forever on a job that already "succeeded" --
`graph/state.py` has no notion of a check that can fail after a done job without going
through `failed.json`, so failing the job itself is what actually produces a retry-after-fix
node (a new `brief_extra`/params -> a new input_hash -> a fresh attempt).

`params.brief_extra["raw_css_injection"]` (test-only escape hatch) lets a caller deliberately
add an off-palette rule to the emitted `brand.css` to exercise the lint failure path without
needing a real design-agent output to go wrong.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from brandkit.compile import compile_css
from brandkit.lint import lint_composition
from brandkit.look import Look
from brandkit.schema import BrandKit

from ...workers.contract import emit
from ..prompts import build_animation_brief
from ._common import add_common_args


def _write_composition(comp_dir: Path, kit: BrandKit, brief_json: str, raw_css_injection: str) -> None:
    comp_dir.mkdir(parents=True, exist_ok=True)
    css = compile_css(kit) + "\n" + raw_css_injection
    (comp_dir / "brand.css").write_text(css, encoding="utf-8")
    (comp_dir / "brief.json").write_text(brief_json, encoding="utf-8")
    (comp_dir / "index.html").write_text(
        '<!doctype html>\n<html><head><link rel="stylesheet" href="brand.css"></head>'
        '<body class="clip" data-duration="1"></body></html>\n',
        encoding="utf-8",
    )
    assets_dir = comp_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    for logo in kit.core_logos.values():
        if not logo.file:
            continue
        src = kit.path / logo.file
        if src.is_file():
            (assets_dir / Path(logo.file).name).write_bytes(src.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    parser.add_argument("--kit-dir", required=True)
    parser.add_argument("--look-path", default=None)
    parser.add_argument("--brief-extra", default="{}")
    parser.add_argument("--out-dir", default="composition")
    args = parser.parse_args(argv)

    kit = BrandKit.load(args.kit_dir)
    look = Look.load(args.look_path) if args.look_path else None
    extra = json.loads(args.brief_extra)
    raw_css_injection = extra.pop("raw_css_injection", "")

    brief_json = build_animation_brief(kit, extra or None, look)
    comp_dir = Path(args.out_dir)
    _write_composition(comp_dir, kit, brief_json, raw_css_injection)

    report = lint_composition(kit, comp_dir)
    (comp_dir / "lint.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report["flags"]:
        detail = "; ".join(f"{f['kind']}: {f['detail']}" for f in report["flags"])
        emit("result", ok=False, detail=f"animation.design: brand lint failed: {detail}")
        return 1

    # Declare every file individually (never the directory itself): `workers.runner`'s
    # artifact verification requires each declared artifact to be a *file*
    # (`_verify_artifacts`: `p.is_file()`), and `queue.artifacts.finalize_success` only
    # moves individually-declared files -- so this is also what actually gets brand.css/
    # brief.json/assets/* (not just index.html) into the final, flat, content-addressed
    # artifact dir, which then doubles as the composition dir for
    # `animation_draft_render.py`/`animation_render.py`.
    import hashlib

    for f in sorted(p for p in comp_dir.rglob("*") if p.is_file()):
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        emit("artifact", path=str(f), role="composition_file", sha256=sha)
    emit("result", ok=True, detail="done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
