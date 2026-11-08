"""derive.py — the style_block DERIVE -> EDIT -> TEST -> ACCEPT loop (T17).

`derive_style` builds a contact-sheet manifest + a prompt asking a vision model to
describe ONLY what a folder of reference images share along the house style axes —
explicitly ignoring subjects, settings, text and logos — and writes the result as a
DRAFT (`style_block.draft.yaml`) for a human to review and hand-edit. Nothing here ever
calls a real model directly; callers supply a `VisionProvider` (see vision.py). Purity
lint (no hex, no quoted text, no over-length block, no named subject) runs on every
derive and is re-checked on accept.

`accept_style` promotes an edited draft into brand.yaml's `stills.style_block` (or a
look file's `style_block`), bumping the style block's version and recording the source
images' hashes in `derived_from`.

No image-processing dependency is added (AGENTS.md: stdlib-first, few dependencies) —
rather than compositing pixels into a literal contact sheet, the "contact sheet" is an
ordered manifest of the image paths; a real `VisionProvider` attaches the image files
themselves.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from .compile import HEX_TOKEN_RE, QUOTE_RE
from .style_axes import load_style_axes
from .vision import VisionProvider
from .yaml_io import dump_roundtrip, load_roundtrip


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_WORDS = 90

# A derived style block that names one of these has failed to "ignore subjects, settings,
# text and logos" per T17 decision 2 — flagged by the purity lint below.
SUBJECT_WORDS = {
    "person", "man", "woman", "people", "office", "desk", "street", "logo", "sign",
    "car", "building", "room", "worker", "employee", "laptop", "phone", "sky", "tree",
}


class DeriveError(ValueError):
    """A derive-style / accept-style step failed."""


def find_images(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        raise DeriveError(f"no such image folder: {folder}")
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not images:
        raise DeriveError(f"no images found in {folder}")
    return images


def build_contact_sheet(image_paths: list[Path]) -> dict:
    """An ordered manifest of the source images — see module docstring for why this
    isn't a literal composited image."""
    return {"count": len(image_paths), "images": [str(p) for p in image_paths]}


def build_derive_prompt(axes: dict[str, Any] | None = None) -> str:
    axes = axes or load_style_axes()
    lines = [
        "You are looking at a set of reference images from one brand's approved footage/stills.",
        "Describe ONLY what these images share along the style axes below. Explicitly ignore "
        "and do not mention: subjects, people's identities, specific settings/locations, any "
        "visible text or logos, and named products.",
        "",
        "Axes:",
    ]
    for key, axis in axes["axes"].items():
        lines.append(f"- {key}: {axis['explanation']}")
    lines += [
        "",
        "Return strict JSON with two top-level keys:",
        '  "axes": {axis_key: one-phrase description, ...} — one entry per axis above',
        f'  "style_block": one paragraph, {MAX_WORDS} words or fewer, condensing the shared style',
        "Never include a hex colour code, a font family name, quoted on-screen text, or any named "
        "subject/setting/product in either value.",
    ]
    return "\n".join(lines)


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def parse_vision_response(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise DeriveError("vision provider response did not contain JSON")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise DeriveError(f"vision provider response was not valid JSON: {exc}") from exc
    if "style_block" not in data or "axes" not in data:
        raise DeriveError("vision provider response missing 'style_block' or 'axes'")
    return data


def lint_style_block_purity(text: str) -> list[str]:
    """Standalone purity check for a derived style block: hex, quotes, over-length, and
    named subjects. (Brand-word/font-name checks run separately, against a real kit, via
    `compile.find_prompt_violations` once the block is wired into a `BrandKit`.)"""
    violations = []
    if HEX_TOKEN_RE.search(text):
        violations.append("contains a hex colour code")
    if QUOTE_RE.search(text):
        violations.append("contains quoted text")
    words = re.findall(r"[A-Za-z']+", text)
    if len(words) > MAX_WORDS:
        violations.append(f"style_block is {len(words)} words, over the {MAX_WORDS}-word cap")
    lower = text.lower()
    hit = sorted(w for w in SUBJECT_WORDS if re.search(rf"\b{re.escape(w)}\b", lower))
    if hit:
        violations.append("names a subject/setting instead of a style trait: " + ", ".join(hit))
    return violations


def draft_path(kit_dir: Path, look_path: Path | None = None) -> Path:
    if look_path is not None:
        return look_path.parent / f"{look_path.stem}.style_block.draft.yaml"
    return kit_dir / "style_block.draft.yaml"


def derive_style(image_folder: str | Path, kit_dir: Path, provider: VisionProvider,
                  look_path: Path | None = None) -> dict:
    """Runs the derive step and always writes a draft file (even a dirty one, so a human
    can see and fix what the model returned) — then raises `DeriveError` if the response
    fails purity lint."""
    images = find_images(image_folder)
    build_contact_sheet(images)
    prompt = build_derive_prompt()
    raw = provider.describe(images, prompt)
    parsed = parse_vision_response(raw)
    style_block = str(parsed["style_block"]).strip()
    violations = lint_style_block_purity(style_block)

    draft = {
        "text": style_block,
        "axes": parsed.get("axes", {}),
        "derived_from": [_sha256_file(p) for p in images],
        "source_folder": str(Path(image_folder).resolve()),
        "purity_violations": violations,
        "status": "draft",
    }
    dpath = draft_path(kit_dir, look_path)
    dpath.write_text(yaml.safe_dump(draft, sort_keys=False), encoding="utf-8")
    if violations:
        raise DeriveError(
            f"derived style_block failed purity lint (draft written to {dpath} for review): "
            + "; ".join(violations)
        )
    return draft


def accept_style(kit_dir: Path, look_path: Path | None = None) -> dict:
    """Promote an edited style_block.draft.yaml into brand.yaml's `stills.style_block`
    (or a look file's `style_block`). Bumps the style block's version, records the
    source images' hashes, and deletes the draft.

    T20: goes through `yaml_io`'s ruamel round-trip loader/dumper, so a hand-annotated
    brand.yaml's comments survive this write."""
    dpath = draft_path(kit_dir, look_path)
    if not dpath.is_file():
        raise DeriveError(f"no draft at {dpath} — run derive-style first")
    draft = yaml.safe_load(dpath.read_bytes()) or {}
    text = str(draft.get("text", "")).strip()
    if not text:
        raise DeriveError(f"{dpath}: draft has no text to accept")
    violations = lint_style_block_purity(text)
    if violations:
        raise DeriveError(f"{dpath}: draft still fails purity lint: {'; '.join(violations)}")

    target_path = look_path if look_path is not None else (kit_dir / "brand.yaml")
    data = load_roundtrip(target_path)
    if data is None:
        data = {}

    if look_path is not None:
        data["style_block"] = text
    else:
        stills = data.setdefault("stills", {})
        prior = stills.get("style_block") or {}
        next_version = str(int(prior.get("version") or 0) + 1)
        stills["style_block"] = {
            "text": text, "version": next_version,
            "derived_from": list(draft.get("derived_from", [])), "status": "filled",
        }

    dump_roundtrip(data, target_path)
    dpath.unlink()
    return data
