"""CLI: `python -m brandkit compile|lint|hash|status|init|derive-style|accept-style|test-style|render-design-system`.

`<kit>` is either a path to a kit directory (one containing `brand.yaml`) or the bare name
of a kit shipped under `packages/brandkit/kits/<name>/`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .compile import CompileError, compile_kit, style_test_prompts
from .derive import DeriveError, accept_style, derive_style, draft_path
from .design_system import cmd_render as _ds_render
from .generate import ClaudeCliTextProvider, GenerateError, init_from_url
from .lint import lint_composition
from .look import Look, LookError
from .schema import BrandKit, BrandKitError
from .status import status_report
from .vision import ClaudeCliVisionProvider
from .yaml_io import dump_roundtrip, load_roundtrip

KITS_ROOT = Path(__file__).resolve().parent.parent / "kits"
TEMPLATE_DIR = KITS_ROOT / "_template"


def resolve_kit_dir(arg: str) -> Path:
    def is_kit(p: Path) -> bool:
        return (p / "design-system" / "design-system.json").is_file() or (p / "brand.yaml").is_file()
    direct = Path(arg)
    if is_kit(direct):
        return direct
    named = KITS_ROOT / arg
    if is_kit(named):
        return named
    raise SystemExit(f"no design-system/ or brand.yaml found for kit '{arg}' (tried {direct} and {named})")


def _look_path(kit_dir: Path, look_name: str | None) -> Path | None:
    if not look_name:
        return None
    return kit_dir / "looks" / f"{look_name}.yaml"


def cmd_compile(args: argparse.Namespace) -> int:
    try:
        kit_dir = resolve_kit_dir(args.kit)
        kit = BrandKit.load(kit_dir)
        look = Look.load(_look_path(kit_dir, args.look)) if args.look else None
        written = compile_kit(kit, args.out, look)
    except (BrandKitError, CompileError, LookError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"out": str(Path(args.out).resolve()),
                       "files": [str(p) for p in written.values()]}, indent=2))
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    try:
        kit = BrandKit.load(resolve_kit_dir(args.kit))
    except BrandKitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    report = lint_composition(kit, args.composition_dir)
    print(json.dumps(report, indent=2))
    return 1 if report["flags"] else 0


def cmd_hash(args: argparse.Namespace) -> int:
    try:
        kit = BrandKit.load(resolve_kit_dir(args.kit))
    except BrandKitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(kit.kit_hash())
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        kit = BrandKit.load(resolve_kit_dir(args.kit))
    except BrandKitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(status_report(kit), indent=2))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    dest = KITS_ROOT / args.client
    if dest.exists():
        print(f"error: {dest} already exists", file=sys.stderr)
        return 1
    if not (TEMPLATE_DIR / "design-system" / "design-system.json").is_file():
        print(f"error: no design-system/ skeleton at {TEMPLATE_DIR}", file=sys.stderr)
        return 1

    if args.from_url:
        try:
            dest = init_from_url(args.client, args.from_url, KITS_ROOT, TEMPLATE_DIR,
                                  text_provider=ClaudeCliTextProvider())
        except GenerateError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        shutil.copytree(TEMPLATE_DIR, dest)
        ds = dest / "design-system"
        for rel in ("README.md", "components/Cover/preview.html"):
            f = ds / rel
            f.write_text(f.read_text(encoding="utf-8").replace("[Client]", args.client.capitalize()), encoding="utf-8")
        for rel in ("design-system.json", "brand-kit.json", "tokens.json"):
            f = ds / rel
            f.write_text(f.read_text(encoding="utf-8").replace("[Client]", args.client.capitalize())
                         .replace('"at": "TEMPLATE"', f'"at": "{datetime.now(timezone.utc).isoformat()}"'), encoding="utf-8")
    if args.guide:
        meta_path = dest / "design-system" / "brand-kit.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["guide"] = {"kind": "style_guide", "ref": args.guide, "fetched_at": datetime.now(timezone.utc).isoformat()}
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"created": str(dest), "brand_system": str(dest / "design-system")}, indent=2))
    return 0


def cmd_derive_style(args: argparse.Namespace) -> int:
    if not args.kit:
        print("error: --kit is required", file=sys.stderr)
        return 1
    kit_dir = resolve_kit_dir(args.kit)
    look_path = _look_path(kit_dir, args.look)
    provider = ClaudeCliVisionProvider()
    try:
        derive_style(args.image_folder, kit_dir, provider, look_path)
    except DeriveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"draft": str(draft_path(kit_dir, look_path))}, indent=2))
    return 0


def cmd_accept_style(args: argparse.Namespace) -> int:
    kit_dir = resolve_kit_dir(args.kit)
    look_path = _look_path(kit_dir, args.look)
    try:
        accept_style(kit_dir, look_path)
    except DeriveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"accepted": str(look_path or (kit_dir / "brand.yaml"))}, indent=2))
    return 0


def cmd_test_style(args: argparse.Namespace) -> int:
    try:
        kit = BrandKit.load(resolve_kit_dir(args.kit))
        look = Look.load(_look_path(resolve_kit_dir(args.kit), args.look)) if args.look else None
        results = style_test_prompts(kit, look)
    except (BrandKitError, CompileError, LookError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps([r.text for r in results], indent=2))
    return 0


def cmd_render_design_system(args: argparse.Namespace) -> int:
    out = _ds_render(args.client, KITS_ROOT)
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m brandkit")
    sub = ap.add_subparsers(dest="command", required=True)

    p_compile = sub.add_parser("compile", help="compile a kit into an out dir")
    p_compile.add_argument("kit")
    p_compile.add_argument("out")
    p_compile.add_argument("--look")
    p_compile.set_defaults(func=cmd_compile)

    p_lint = sub.add_parser("lint", help="lint a composition dir against a kit")
    p_lint.add_argument("kit")
    p_lint.add_argument("composition_dir")
    p_lint.set_defaults(func=cmd_lint)

    p_hash = sub.add_parser("hash", help="print a kit's content hash")
    p_hash.add_argument("kit")
    p_hash.set_defaults(func=cmd_hash)

    p_status = sub.add_parser("status", help="print a kit's fillable-field readiness report")
    p_status.add_argument("kit")
    p_status.set_defaults(func=cmd_status)

    p_init = sub.add_parser("init", help="start a Brand System for a client from kits/_template/design-system/, optionally filled from a site")
    p_init.add_argument("client")
    p_init.add_argument("--from", dest="from_url", default=None,
                         help="a client site URL to fetch and draft the whole kit from (guessed:true throughout)")
    p_init.add_argument("--guide", default=None, help="a style-guide file (.md) to fold in as extra context")
    p_init.set_defaults(func=cmd_init)

    p_derive = sub.add_parser("derive-style", help="derive a DRAFT style_block from a folder of images")
    p_derive.add_argument("image_folder")
    p_derive.add_argument("--kit", required=True)
    p_derive.add_argument("--look")
    p_derive.set_defaults(func=cmd_derive_style)

    p_accept = sub.add_parser("accept-style", help="promote a DRAFT style_block into the kit/look")
    p_accept.add_argument("kit")
    p_accept.add_argument("--look")
    p_accept.set_defaults(func=cmd_accept_style)

    p_test_style = sub.add_parser("test-style", help="print six unrelated-subject still prompts, no generation")
    p_test_style.add_argument("kit")
    p_test_style.add_argument("--look")
    p_test_style.set_defaults(func=cmd_test_style)

    p_render = sub.add_parser("render-design-system", help="render kits/<client>/design-system/index.html, a self-contained brand guide")
    p_render.add_argument("client")
    p_render.set_defaults(func=cmd_render_design_system)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
