"""design_system.py — the Brand System (a Design System artifact exported to
`kits/<client>/design-system/`) is the source of truth; brand.yaml is derived from it.

Two entry points, both pure functions of that folder:

  pull_brand_yaml(folder) -> str    the kit as brand.yaml text, built in memory by BrandKit.load()
                                    whenever kits/<client>/design-system/ exists. No brand.yaml file
                                    is written; nothing is authored twice.
  render_html(folder) -> str        one self-contained index.html a person can open anywhere:
                                    the brand book, every section, tokens, type, logos and the
                                    live component previews, no server and no build step.

brand-kit.json holds only what a design system cannot say about itself and code must know:
  identity (two sentences), colours (which token is which role, and its name in words),
  personality (adjectives, one voice sentence), logos (slot -> file), and `guessed`.
Everything else is a convention of the template, fixed here:
  tokens.json type.families.sans      -> core.typography heading and body (Google-hosted)
  tokens surface/surface-raised/muted/line -> animation.css_vars
  imagery.md "## stills.style_block"  -> stills.style_block.text (the blockquote under it)
  primary on light, accent on dark    -> animation.caption_style.palette
  logo placements                     -> DEFAULT_LOGO_PLACEMENTS (a video setting, not a brand fact)
World, accents, camera, pacing, grid notes and sfx are emitted `status: pending`: the beat
decides those, not the brand.

A value still holding the template's `[bracketed placeholder]` (identity, voice, the style
block) is emitted `pending`, never filled, so an untouched skeleton cannot pass as a brand
(T32: compile refuses a still or video prompt while `stills.style_block` is pending). The kit's
`name` is its folder (`kits/<client>/`), the slug `init` was given. The derived text holds no
date, so `kit_hash()` changes only when the Brand System does.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import re
from pathlib import Path

import yaml

CSS_VARS = {"surface": "surface", "surface_2": "surface-raised", "ink_dim": "muted",
            "hairline": "line", "border": "line", "line_off": "line"}
DEFAULT_LOGO_PLACEMENTS = {
    "16:9": {"position": "top-left", "inset_px": 64, "height_px": 40},
    "9:16": {"position": "top-center", "inset_px": 96, "height_px": 44},
}


# ---- reading the design system ----------------------------------------------------------

def _load(folder: Path) -> dict:
    tokens = json.loads((folder / "tokens.json").read_text(encoding="utf-8"))
    meta = json.loads((folder / "brand-kit.json").read_text(encoding="utf-8"))
    index = json.loads((folder / "design-system.json").read_text(encoding="utf-8"))
    readme = (folder / "README.md").read_text(encoding="utf-8").split("\n---\n")[0]
    sections = {p.stem: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.md")) if p.name != "README.md"}
    return {"tokens": tokens, "meta": meta, "index": index, "readme": readme, "sections": sections}


def token_value(tokens: dict, name: str, theme: str = "light", _depth: int = 0) -> str | None:
    """Resolve a colour token to a hex for one theme, following `{alias}` references."""
    for t in tokens["color"]["tokens"]:
        if t["name"] != name:
            continue
        v = t["value"]
        if isinstance(v, dict):
            first = tokens["color"]["themes"][0]["id"]
            v = v.get(theme, v.get(first))
        if isinstance(v, str) and v.startswith("{") and v.endswith("}") and _depth < 16:
            return token_value(tokens, v[1:-1], theme, _depth + 1)
        return v
    return None


def style_block(sections: dict, heading: str) -> str | None:
    """The blockquote directly under `## <heading>` in any section file."""
    for text in sections.values():
        m = re.search(rf"^##\s+{re.escape(heading)}\s*$\n+((?:>.*\n?)+)", text, re.M)
        if m:
            lines = [l[1:].strip() for l in m.group(1).splitlines() if l.startswith(">")]
            return " ".join(l for l in lines if l)
    return None


# ---- brand.yaml ---------------------------------------------------------------------------

_GUESSED = False  # set per pull from brand-kit.json "guessed"


def _filled(**kw) -> dict:
    return {**kw, "status": "filled", "guessed": _GUESSED}


def is_placeholder(text) -> bool:
    """True for nothing at all, or a template slot like `[Client]` or `[Under 90 words, ...]`."""
    return not text or bool(re.fullmatch(r"\[[^\[\]]*\]", str(text).strip()))


def _text_or_pending(text) -> dict:
    return _pending(text=None) if is_placeholder(text) else _filled(text=text)


def _sources(meta: dict, index: dict) -> list[dict]:
    """Where the kit came from, as recorded in brand-kit.json: the live Brand System artifact,
    the site `init --from` read (`source`), a style guide `init --guide` folded in (`guide`)."""
    out = []
    if meta.get("artifact"):
        out.append({"kind": "style_guide", "ref": meta["artifact"],
                    "fetched_at": (index.get("lastChange") or {}).get("at")})
    for key in ("source", "guide"):
        if isinstance(meta.get(key), dict) and meta[key].get("ref"):
            out.append({k: meta[key].get(k) for k in ("kind", "ref", "fetched_at")})
    return out


def _items(items: list) -> dict:
    out = {"items": list(items or []), "status": "filled" if items else "pending"}
    if items and _GUESSED:  # only a guessed kit gains the key, so confirmed kits hash unchanged
        out["guessed"] = True
    return out


def _pending(**kw) -> dict:
    return {**kw, "status": "pending", "guessed": False}


def pull_brand_yaml(folder: str | Path, version: str = "5") -> str:
    global _GUESSED
    d = _load(Path(folder))
    tokens, meta = d["tokens"], d["meta"]
    _GUESSED = bool(meta.get("guessed", False))
    fam = tokens["type"]["families"]
    family_name = lambda key: re.match(r'\s*"?([^",]+)"?', fam[key]).group(1).strip()
    identity = meta["identity"]
    official = [] if is_placeholder(identity.get("name")) else [identity["name"]]

    colours = {
        role: _filled(name_plain=spec["name_plain"], hex=token_value(tokens, spec["token"]).upper()[:7])
        for role, spec in meta["colours"].items()
    }
    logos = {
        slot: _filled(file=f"design-system/{file}", clear_space=0.25, min_size_px=24, placements=DEFAULT_LOGO_PLACEMENTS)
        for slot, file in meta.get("logos", {}).items()
    } or {"primary": {"file": None, "clear_space": None, "min_size_px": None, "placements": {}, "status": "pending", "guessed": False}}
    css_vars = {k: _filled(value=token_value(tokens, tok)) for k, tok in CSS_VARS.items() if token_value(tokens, tok)}
    sb = style_block(d["sections"], "stills.style_block")
    sb = None if is_placeholder(sb) else sb
    # Captions are a pipeline setting, not a brand rule: the kit's caption_style is derived
    # from the palette roles (accent on dark, primary on light) unless brand-kit.json overrides it.
    cap = {"font_role": "heading", "brand_light": meta["colours"]["primary"]["token"],
           "brand_dark": meta["colours"]["accent"]["token"]}

    kit = {
        "name": Path(folder).resolve().parent.name,
        "version": version,
        "core": {
            "identity": {
                "name": _text_or_pending(identity.get("name")),
                "what_they_do": _text_or_pending(identity.get("what_they_do")),
                "who_they_serve": _text_or_pending(identity.get("who_they_serve")),
            },
            "colours": {"items": colours, "world_tone": meta["world_tone"], "dominant": meta["dominant"]},
            "typography": {role: _filled(family=family_name("sans"), source="google", file=None)
                           for role in ("heading", "body")},
            "logos": logos,
            "personality": {"is": _items(meta["personality"].get("is")),
                            "voice": _text_or_pending(meta["personality"].get("voice"))},
            "world": {k: _items([]) for k in ("places", "people", "objects", "textures")},
            "names": {"official": _items(official),
                      "products": {"items": [], "status": "pending"}, "pronunciation": []},
            "sources": _sources(meta, d["index"]),
        },
        "stills": {
            "style_block": ({"text": sb, "version": str(tokens.get("version", 1)), "derived_from": [],
                             "status": "filled", "guessed": _GUESSED} if sb else
                            {"text": None, "version": None, "derived_from": [], "status": "pending"}),
            "accents": _pending(text=None),
        },
        "video": {"camera_personality": _pending(text=None), "pacing_default": _pending(text=None)},
        "animation": {
            "grid_safe_areas": _pending(text=None),
            "easing": _filled(text="Matches house default (power2.out, decelerate on entrance / accelerate on exit)."),
            "durations": _filled(text="Matches house default duration scale (micro/standard/slow/hold)."),
            "colour_ratio": _pending(text=None),
            "caption_style": {"font_role": cap["font_role"],
                              "palette": {"dark": {"brand": token_value(tokens, cap["brand_dark"]).upper()[:7]},
                                          "light": {"brand": token_value(tokens, cap["brand_light"]).upper()[:7]}},
                              "band": 0.905, "max_words": 6, "font_scale": 1.0, "status": "filled", "guessed": _GUESSED},
            "sfx_palette": {"items": [], "status": "pending"},
            "css_vars": css_vars,
        },
        "qa_checklist_extra": [],
    }
    header = ("# DERIVED in memory by BrandKit.load() from kits/<client>/design-system/. "
              "Never written to disk on purpose: change the Brand System, not this.\n")
    return header + yaml.safe_dump(kit, sort_keys=False, allow_unicode=True, width=100)


# ---- index.html --------------------------------------------------------------------------

def _md(text: str) -> str:
    """Small Markdown subset: headings, paragraphs, bullets, pipe tables, blockquotes, fences, inline."""
    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"): j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>"); i = j + 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)", l)
        if m:
            n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>"); i += 1; continue
        if l.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells): rows.append(cells)
                i += 1
            head, body = rows[0], rows[1:]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>")
            continue
        if l.startswith(">"):
            q = []
            while i < len(lines) and lines[i].startswith(">"): q.append(lines[i][1:].strip()); i += 1
            out.append("<blockquote>" + inline(" ".join(q)) + "</blockquote>"); continue
        if re.match(r"^\s*[-*]\s+", l):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i])); i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>"); continue
        if l.strip() == "": i += 1; continue
        p = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||>|```|\s*[-*]\s)", lines[i]):
            p.append(lines[i]); i += 1
        out.append("<p>" + inline(" ".join(p)) + "</p>")
    return "\n".join(out)


def tokens_css(tokens: dict) -> str:
    themes = [t["id"] for t in tokens["color"]["themes"]]
    first = themes[0]
    def val(t, theme):
        v = t["value"]
        if isinstance(v, dict): v = v.get(theme, v.get(first))
        return f"var(--{v[1:-1]})" if isinstance(v, str) and v.startswith("{") else v
    css = [f":root, [data-theme=\"{first}\"] {{"] + [f"  --{t['name']}: {val(t, first)};" for t in tokens["color"]["tokens"]] + ["}"]
    for th in themes[1:]:
        css += [f"[data-theme=\"{th}\"] {{"] + [f"  --{t['name']}: {val(t, th)};" for t in tokens["color"]["tokens"] if isinstance(t["value"], dict)] + ["}"]
    css.append(":root {")
    for fam in ("spacing", "radius"):
        css += [f"  --{t['name']}: {t['value']};" for t in tokens.get(fam, {}).get("tokens", [])]
    css += [f"  --font-{k}: {v};" for k, v in tokens["type"]["families"].items()] + ["}"]
    for g in tokens["type"]["groups"]:
        for s in g["styles"]:
            css.append(f".{s['name']} {{ font-family: var(--font-{g['family']}); font-size: {s['fontSize']}; line-height: {s['lineHeight']}; "
                       f"font-weight: {s['fontWeight']}; letter-spacing: {s.get('letterSpacing', '0')}; }}")
    return "\n".join(css)


def render_html(folder: str | Path) -> str:
    folder = Path(folder)
    d = _load(folder)
    tokens, index = d["tokens"], d["index"]
    title = index.get("title", tokens.get("name", "Brand System"))
    tcss = tokens_css(tokens)
    fonts = "".join(f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={html.escape(f)}:wght@400;500;700&display=swap">'
                    for f in {re.match(r'\s*"?([^",]+)"?', v).group(1).strip().replace(" ", "+") for v in tokens["type"]["families"].values()})

    def swatch(t):
        v = t["value"]; light = token_value(tokens, t["name"], "light"); dark = token_value(tokens, t["name"], "dark")
        return (f'<div class="tok"><span class="sw" style="background:{light}"></span>'
                + (f'<span class="sw" style="background:{dark}"></span>' if dark != light else '<span class="sw none"></span>')
                + f'<code>{t["name"]}</code><small>{html.escape(str(light))}{" / " + html.escape(str(dark)) if dark != light else ""}</small>'
                + f'<p>{html.escape(t.get("usage", ""))}</p></div>')
    colours = "".join(swatch(t) for t in tokens["color"]["tokens"])
    types = "".join(f'<div class="ty"><div class="{s["name"]}" style="max-width:100%;overflow:hidden">{html.escape(s.get("sample", s["name"]))}</div>'
                    f'<small><code>{s["name"]}</code> {s["fontSize"]} / {s["lineHeight"]} · {s["fontWeight"]}</small><p>{html.escape(s.get("usage", ""))}</p></div>'
                    for g in tokens["type"]["groups"] for s in g["styles"])
    scale = "".join(f'<div class="tok"><code>{t["name"]}</code><small>{t["value"]}</small><p>{html.escape(t.get("usage", ""))}</p></div>'
                    for fam in ("spacing", "radius") for t in tokens.get(fam, {}).get("tokens", []))

    logos = ""
    for group in index.get("groups", []):
        gdir = folder / "assets" / group
        if not gdir.exists(): continue
        order = index["assetGroups"].get(group, {}).get("order") or sorted(p.name for p in gdir.iterdir() if p.suffix == ".svg")
        cards = ""
        for name in order:
            p = gdir / name
            if p.suffix.lower() == ".svg" and p.exists():
                svg = re.sub(r"<\?xml[^>]*\?>|<metadata>.*?</metadata>", "", p.read_text(encoding="utf-8"), flags=re.S)
                cards += f'<figure><div class="logo">{svg}</div><figcaption><code>{name}</code></figcaption></figure>'
            elif p.suffix.lower() == ".html":
                cards += f'<figure><figcaption><code>{name}</code> · <a href="assets/{group}/{name}">open composition</a></figcaption></figure>'
        note = (gdir / "README.md")
        logos += f'<section><h2>{html.escape(group)}</h2>{_md(note.read_text(encoding="utf-8")) if note.exists() else ""}<div class="logos">{cards}</div></section>'

    comps = ""
    for cdir in sorted((folder / "components").iterdir()):
        pv = cdir / "preview.html"
        if not pv.exists() or cdir.name == "Cover": continue
        src = pv.read_text(encoding="utf-8")
        hm = re.search(r"height=(\d+)", src.splitlines()[0]); h = int(hm.group(1)) if hm else 240
        doc = f"<!doctype html><html data-theme=\"light\"><head><meta charset=utf-8><style>{tcss}</style></head><body>{src}</body></html>"
        readme = cdir / "README.md"
        comps += (f'<section><h2>{cdir.name}</h2>{_md(readme.read_text(encoding="utf-8")) if readme.exists() else ""}'
                  f'<iframe title="{cdir.name}" style="height:{h + 8}px" srcdoc="{html.escape(doc, quote=True)}"></iframe></section>')
    cover = folder / "components" / "Cover" / "preview.html"
    cover_html = ""
    if cover.exists():
        doc = f"<!doctype html><html data-theme=\"light\"><head><meta charset=utf-8><style>{tcss}</style></head><body>{cover.read_text(encoding='utf-8')}</body></html>"
        cover_html = f'<iframe class="cover" title="Cover" srcdoc="{html.escape(doc, quote=True)}"></iframe>'

    sections = "".join(f'<section class="doc">{_md(t)}</section>' for t in d["sections"].values())
    glance = _at_a_glance(folder, tokens, d["meta"])
    page_css = """
    :root{--pg:#fff;--pi:#0b1440;--pm:#4a5578;--pl:#d5deef;--pr:#f2f5fd}
    @media (prefers-color-scheme:dark){:root{--pg:#080f2e;--pi:#eef2ff;--pm:#aab6d9;--pl:#26326b;--pr:#111a48}}
    *{box-sizing:border-box}body{margin:0;background:var(--pg);color:var(--pi);font:16px/1.55 var(--font-sans, system-ui, sans-serif);padding:0 16px 80px}
    main{max-width:1040px;margin:0 auto}h1{font-size:44px;line-height:1;letter-spacing:-.02em;margin:40px 0 8px}h2{font-size:26px;margin:48px 0 12px;letter-spacing:-.01em}
    h3{font-size:18px;margin:24px 0 8px}p{max-width:70ch}ul{padding-left:20px}li{margin:4px 0}code{font-size:.9em;background:var(--pr);padding:1px 5px;border-radius:4px}
    table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--pl);vertical-align:top}
    blockquote{margin:12px 0;padding:14px 18px;background:var(--pr);border-radius:12px;max-width:70ch}pre{background:var(--pr);padding:14px;border-radius:12px;overflow:auto}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}.tok{border:1px solid var(--pl);border-radius:12px;padding:12px}.tok p{font-size:13px;color:var(--pm);margin:6px 0 0}
    .sw{display:inline-block;width:40px;height:40px;border-radius:50%;margin-right:6px;border:1px solid var(--pl)}.sw.none{visibility:hidden}.tok code{display:block;margin-top:6px}.tok small{color:var(--pm)}
    .ty{border-bottom:1px solid var(--pl);padding:14px 0}.ty p{font-size:13px;color:var(--pm);margin:4px 0 0}.ty small{color:var(--pm)}
    .logos{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}figure{margin:0;border:1px solid var(--pl);border-radius:12px;padding:12px;background:
    repeating-conic-gradient(var(--pr) 0 25%,transparent 0 50%) 0 0/16px 16px}.logo svg{width:100%;height:auto;display:block}figcaption{font-size:12px;margin-top:8px;color:var(--pm)}
    iframe{width:100%;border:1px solid var(--pl);border-radius:12px;background:#fff}iframe.cover{aspect-ratio:960/288;height:auto;margin-top:24px}
    .meta{color:var(--pm);font-size:13px}.look{max-width:100%;max-height:420px;border-radius:12px;border:1px solid var(--pl);display:block}
    """
    last = index.get("lastChange", {})
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>{fonts}<style>{tcss}\n{page_css}</style></head><body><main>
<h1>{html.escape(title)}</h1><p class="meta">{('Source of truth: <a href="' + html.escape(d['meta']['artifact']) + '">the live Brand System</a>. ') if d['meta'].get('artifact') else ''}Rendered on {_dt.date.today().isoformat()}{('; last change ' + html.escape(str(last.get('at', ''))) + ' by ' + html.escape(str(last.get('by', ''))) + ': ' + html.escape(str(last.get('note', '')))) if last else ''}.</p>
{cover_html}
{glance}
<section class="doc">{_md(d['readme'])}</section>
{sections}
<section><h2>Color</h2><div class="grid">{colours}</div></section>
<section><h2>Type</h2>{types}</section>
<section><h2>Spacing and radius</h2><div class="grid">{scale}</div></section>
{logos}
{comps}
</main></body></html>"""


def _at_a_glance(folder: Path, tokens: dict, meta: dict) -> str:
    """T41: the brand's colours by role with their names in words, and the approved look
    (`assets/approved-look-*.png`) when the kit has one -- what a person checks first."""
    named = ""
    for role, c in (meta.get("colours") or {}).items():
        if not isinstance(c, dict) or not c.get("token"):
            continue
        value = token_value(tokens, c["token"], "light")
        named += (f'<div class="tok" data-colour-role="{html.escape(role)}"><span class="sw" style="background:{html.escape(str(value))}"></span>'
                  f'<code>{html.escape(role.replace("_", " "))}</code><small>{html.escape(str(c.get("name_plain", "")))} · {html.escape(str(value))}</small></div>')
    looks = "".join(f'<figure><img class="look" src="assets/{html.escape(p.name)}" alt="Approved look"><figcaption><code>{html.escape(p.name)}</code></figcaption></figure>'
                    for p in sorted((folder / "assets").glob("approved-look-*.png")))
    if not named and not looks:
        return ""
    return (f'<section><h2>At a glance</h2>{f"<div class=grid>{named}</div>" if named else ""}'
            f'{f"<h3>Approved look</h3>{looks}" if looks else ""}</section>')


# ---- CLI --------------------------------------------------------------------------------------

def kit_folder(client: str, kits_dir: Path) -> Path:
    return kits_dir / client / "design-system"


def cmd_render(client: str, kits_dir: Path) -> Path:
    folder = kit_folder(client, kits_dir)
    (folder / "tokens.css").write_text(tokens_css(_load(folder)["tokens"]), encoding="utf-8")
    out = folder / "index.html"
    out.write_text(render_html(folder), encoding="utf-8")
    return out
