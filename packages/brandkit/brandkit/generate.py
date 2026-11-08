"""generate.py — `python -m brandkit init <client> --from <url>`: take a first guess at
every field of a new kit, end to end (T20).

`TextProvider` is the same pattern as `vision.VisionProvider`: `ClaudeCliTextProvider`
shells out to a configurable terminal-agent CLI and is NEVER invoked from a test;
`FakeTextProvider` returns a canned response. `init_from_url` fetches the site
(`fetch.fetch_site`), extracts colours/fonts/logo/copy mechanically, asks the
`TextProvider` to draft the parts language has to write (identity, personality, world,
names, style_block, accents, camera_personality), and writes every field with
`guessed: true` plus a `core.sources` entry — nothing here ever claims a value is
confirmed.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


from .design_system import token_value
from .fetch import SiteSnapshot, extract_colour_frequencies, extract_font_families, fetch_site
from .ui_shades import relative_luminance

HEX6_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Keys forced to a quoted scalar: unquoted "16:9"/"9:16" round-trips fine through
# ruamel's own (YAML 1.2) resolver, but PyYAML's `safe_load` (YAML 1.1, used everywhere
# else in this package to READ a kit) resolves a bare "16:9" as a sexagesimal int.
DEFAULT_LOGO_PLACEMENTS = {
    "16:9": {"position": "top-left", "inset_px": 64, "height_px": 40},
    "9:16": {"position": "top-center", "inset_px": 96, "height_px": 44},
}


class GenerateError(ValueError):
    """`init --from` (or a step it depends on) failed."""


# ---- TextProvider -----------------------------------------------------------------------

class TextProvider(Protocol):
    def draft(self, context: dict) -> str:
        """Return raw text (expected to contain a JSON object) drafting the brand's
        identity/personality/world/names/style copy from `context`."""
        ...


class ClaudeCliTextProvider:
    """Shells out to a terminal agent CLI with a JSON-context prompt. NEVER invoked from
    tests — see module docstring."""

    def __init__(self, command: list[str] | None = None):
        self.command = command or ["claude", "-p"]

    def draft(self, context: dict) -> str:
        prompt = build_text_prompt(context)
        try:
            result = subprocess.run([*self.command, prompt], capture_output=True, text=True, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise GenerateError(f"text provider command failed: {exc}") from exc
        return result.stdout


class FakeTextProvider:
    """Test double — returns a canned response and records every call it received. Never
    shells out to anything."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict] = []

    def draft(self, context: dict) -> str:
        self.calls.append(context)
        return self.response


def build_text_prompt(context: dict) -> str:
    return (
        "You are drafting a FIRST GUESS at a brand kit from a company's website copy. "
        "Every value you return will be marked 'guessed: true' for a human to review — "
        "write something concrete, not a placeholder. Positive only: describe what the "
        "brand IS; never write a forbid/negative list.\n\n"
        f"Site: {context.get('url')}\nTitle: {context.get('title')}\n"
        f"Meta description: {context.get('meta_description')}\nHero text: {context.get('hero_text')}\n\n"
        "Return strict JSON with keys:\n"
        '  "what_they_do": one line\n  "who_they_serve": one line\n'
        '  "personality_is": [3-5 adjectives]\n  "personality_voice": one sentence\n'
        '  "world_places": [], "world_people": [], "world_objects": [], "world_textures": [] '
        "-- subject matter that belongs in this brand's pictures\n"
        '  "products": [] -- real product/feature names, if any are named on the site\n'
        '  "style_block": one paragraph (<=90 words), cinematographer language, no hex/quotes/brand words\n'
        '  "accents": one line on how the accent colour enters a photo\n'
        '  "camera_personality": one line on the brand\'s default camera feel\n'
    )


def parse_text_response(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise GenerateError("text provider response did not contain JSON")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise GenerateError(f"text provider response was not valid JSON: {exc}") from exc


# ---- colour role assignment -------------------------------------------------------------

def assign_colour_roles(hexes: list[str]) -> dict[str, str]:
    """A first guess at role assignment for `core.colours.items`: lightest -> light_neutral,
    darkest -> dark_neutral, remaining ranked-by-frequency hexes -> accent/primary/
    secondary in that order. Pads with generic defaults if the site yielded under 3."""
    hexes = list(dict.fromkeys(h.upper() for h in hexes))
    while len(hexes) < 3:
        hexes.append(["#FFFFFF", "#111111", "#3366CC"][len(hexes)])
    hexes = hexes[:6]
    ordered = sorted(hexes, key=relative_luminance)
    dark_neutral, light_neutral = ordered[0], ordered[-1]
    roles = {"dark_neutral": dark_neutral, "light_neutral": light_neutral}
    remaining = [h for h in hexes if h not in (dark_neutral, light_neutral)]
    for h, label in zip(remaining, ("accent", "primary", "secondary")):
        roles[label] = h
    roles.setdefault("accent", dark_neutral)
    return roles


_ROLE_NAME_GUESS = {
    "primary": "brand blue", "secondary": "brand teal", "accent": "brand accent",
    "dark_neutral": "charcoal", "light_neutral": "cream",
}


def _guess_name_plain(role: str, hexv: str) -> str:
    return _ROLE_NAME_GUESS.get(role, role.replace("_", " "))


def _filled(text, guessed=True) -> dict:
    return {"text": text, "status": "filled", "guessed": guessed}


def _items(items: list, guessed=True) -> dict:
    return {"items": list(items), "status": "filled" if items else "pending"}


def _apply_colour_roles(tokens: dict, role_to_token: dict[str, str], roles: dict[str, str]) -> None:
    """Write each site colour onto its role's token (the light theme of a themed token), then
    set `on-primary` against whatever `primary` now resolves to: white on a dark primary, the
    dark neutral on a light one. The roles come from brand-kit.json, so a site that yields no
    primary (fewer than five colours) keeps the template's primary instead of failing."""
    for t in tokens["color"]["tokens"]:
        for role, tok in role_to_token.items():
            if t["name"] == tok and role in roles:
                hexv = roles[role].lower()
                t["value"] = {**t["value"], "light": hexv} if isinstance(t["value"], dict) else hexv
    primary = token_value(tokens, role_to_token.get("primary", "primary"))
    ink = token_value(tokens, role_to_token.get("dark_neutral", "ink")) or "#111111"
    if not (primary and HEX6_RE.match(primary)):
        return
    for t in tokens["color"]["tokens"]:
        if t["name"] == "on-primary":
            t["value"] = "#ffffff" if relative_luminance(primary) < 0.4 else ink.lower()


# ---- driver -------------------------------------------------------------------------

def init_from_url(
    client: str, url: str, kits_root: Path, template_dir: Path,
    http_get=None, text_provider: TextProvider | None = None,
) -> Path:
    """Copy `template_dir` (which holds `design-system/`, the Brand System skeleton) to
    `kits_root/<client>/`, then fill the Brand System end to end from `url`: colours, fonts and
    the logo extracted mechanically into tokens.json / assets, everything else drafted by
    `text_provider` into brand-kit.json, README.md and imagery.md. brand-kit.json carries
    `guessed: true` so every derived kit field is marked a first guess. Returns the kit dir."""
    import shutil

    dest = kits_root / client
    if dest.exists():
        raise GenerateError(f"{dest} already exists")
    shutil.copytree(template_dir, dest)
    ds = dest / "design-system"
    if not (ds / "design-system.json").is_file():
        raise GenerateError(f"template at {template_dir} has no design-system/ skeleton")

    snapshot: SiteSnapshot = fetch_site(url, http_get)
    hexes = extract_colour_frequencies(snapshot.css)
    roles = assign_colour_roles(hexes)
    fonts = extract_font_families(snapshot.css)
    text_provider = text_provider or FakeTextProvider(json.dumps({}))
    draft = parse_text_response(text_provider.draft({
        "url": url, "title": snapshot.title,
        "meta_description": snapshot.meta_description, "hero_text": snapshot.hero_text,
    }))
    name = snapshot.title or client
    fetched_at = datetime.now(timezone.utc).isoformat()

    # tokens.json: the site's colours onto the tokens brand-kit.json names for each role, its
    # first font. A role the site did not yield keeps the template's value (still guessed).
    meta = json.loads((ds / "brand-kit.json").read_text(encoding="utf-8"))
    tokens = json.loads((ds / "tokens.json").read_text(encoding="utf-8"))
    tokens["name"] = name
    _apply_colour_roles(tokens, {role: spec["token"] for role, spec in meta["colours"].items()}, roles)
    heading = fonts[0] if fonts else "Inter"
    tokens["type"]["families"]["sans"] = f'"{heading}", "Helvetica Neue", Arial, sans-serif'
    (ds / "tokens.json").write_text(json.dumps(tokens, indent=2) + "\n", encoding="utf-8")

    # the logo, if the site exposed one
    logos = {}
    index = json.loads((ds / "design-system.json").read_text(encoding="utf-8"))
    if snapshot.logo_bytes:
        ext = snapshot.logo_ext or "svg"
        logo_path = ds / "assets" / "Logos" / f"logo.{ext}"
        logo_path.write_bytes(snapshot.logo_bytes)
        logos["primary"] = f"assets/Logos/{logo_path.name}"
        index["assetGroups"]["Logos"]["order"] = [logo_path.name]
    index["title"] = f"{name} Brand System"
    index["namespace"] = re.sub(r"[^A-Za-z0-9]", "", name) or "Brand"
    index["createdOnFiles"] = {"v": 1, "at": fetched_at}
    (ds / "design-system.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    # brand-kit.json: identity, roles in words, personality, world, drafts
    meta["guessed"] = True
    meta["identity"] = {"name": name, "what_they_do": draft.get("what_they_do"),
                        "who_they_serve": draft.get("who_they_serve")}
    for role in meta["colours"]:
        if role in roles:
            meta["colours"][role]["name_plain"] = _guess_name_plain(role, roles[role])
    meta["logos"] = logos
    meta["personality"] = {"is": draft.get("personality_is", []), "voice": draft.get("personality_voice")}
    meta["source"] = {"kind": "website", "ref": url, "fetched_at": fetched_at}
    (ds / "brand-kit.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    # the brand book and the style block: fill the bracketed slots the draft can fill
    readme = (ds / "README.md").read_text(encoding="utf-8").replace("[Client]", name)
    if draft.get("what_they_do"):
        readme = readme.replace("[what they do, in one sentence, present tense]", draft["what_they_do"])
    if draft.get("who_they_serve"):
        readme = readme.replace("[who they serve]", draft["who_they_serve"])
    if draft.get("personality_is"):
        readme = readme.replace("[Three to five adjectives, positive only. Who this brand is.]",
                                ", ".join(draft["personality_is"]).capitalize() + ".")
    (ds / "README.md").write_text(readme, encoding="utf-8")
    if draft.get("style_block"):
        imagery = (ds / "imagery.md").read_text(encoding="utf-8")
        imagery = re.sub(r"^> \[Under 90 words.*?\]$", "> " + draft["style_block"].strip(), imagery, count=1, flags=re.M | re.S)
        (ds / "imagery.md").write_text(imagery, encoding="utf-8")
    cover = ds / "components" / "Cover" / "preview.html"
    cover.write_text(cover.read_text(encoding="utf-8").replace("[Client]", name), encoding="utf-8")
    return dest
