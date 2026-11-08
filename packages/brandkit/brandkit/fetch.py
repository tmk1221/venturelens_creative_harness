"""fetch.py — pull one client site's HTML + linked CSS for `brandkit init --from` (T20).

stdlib only (urllib). Real network access happens exclusively through the `http_get`
callable, which every caller may override — tests always pass a fake fetcher reading
saved fixture HTML/CSS from disk (AGENTS.md: tests never touch the network). Sizes are
capped so a pathological page can't blow up memory or a test run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

MAX_PAGE_BYTES = 2_000_000
MAX_CSS_FILES = 5
MAX_CSS_BYTES = 500_000
TIMEOUT_S = 10

HttpGet = Callable[[str], bytes]

LINK_CSS_RE = re.compile(r'<link[^>]+rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']', re.I)
STYLE_TAG_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.I | re.S)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
META_DESC_RE = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', re.I)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
IMG_LOGO_RE = re.compile(r'<img[^>]+(?:class|id)=["\'][^"\']*logo[^"\']*["\'][^>]*\ssrc=["\']([^"\']+)["\']', re.I | re.S)
SVG_LOGO_RE = re.compile(r'(<svg\b[^>]*(?:class|id)=["\'][^"\']*logo[^"\']*["\'][^>]*>.*?</svg>)', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def default_http_get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "brandkit-init/1 (+https://github.com)"})
    with urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 — deliberate, capped read
        return resp.read(MAX_PAGE_BYTES + 1)[:MAX_PAGE_BYTES]


def _strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", s)).strip()


@dataclass
class SiteSnapshot:
    url: str
    html: str
    css: str
    title: str
    meta_description: str
    hero_text: str
    logo_bytes: bytes | None
    logo_ext: str | None


def fetch_site(url: str, http_get: HttpGet | None = None) -> SiteSnapshot:
    """One page + its linked CSS (capped), never JS-rendered. `http_get` defaults to a
    real urllib fetch; tests always inject a fake one."""
    get = http_get or default_http_get
    raw = get(url)
    html = raw.decode("utf-8", errors="replace")[:MAX_PAGE_BYTES]

    css_parts = [m.group(1) for m in STYLE_TAG_RE.finditer(html)]
    for href in list(dict.fromkeys(m.group(1) for m in LINK_CSS_RE.finditer(html)))[:MAX_CSS_FILES]:
        css_url = urljoin(url, href)
        try:
            css_bytes = get(css_url)
        except Exception:  # noqa: BLE001 — a missing/broken stylesheet just contributes nothing
            continue
        css_parts.append(css_bytes.decode("utf-8", errors="replace")[:MAX_CSS_BYTES])
    css = "\n".join(css_parts)[:MAX_CSS_BYTES]

    title_m = TITLE_RE.search(html)
    meta_m = META_DESC_RE.search(html)
    h1_m = H1_RE.search(html)

    logo_bytes: bytes | None = None
    logo_ext: str | None = None
    svg_m = SVG_LOGO_RE.search(html)
    if svg_m:
        logo_bytes = svg_m.group(1).encode("utf-8")
        logo_ext = "svg"
    else:
        img_m = IMG_LOGO_RE.search(html)
        if img_m:
            logo_url = urljoin(url, img_m.group(1))
            try:
                logo_bytes = get(logo_url)
                logo_ext = logo_url.rsplit(".", 1)[-1].split("?")[0].lower()[:4] or "png"
            except Exception:  # noqa: BLE001 — a missing logo image just leaves this pending
                logo_bytes = None

    return SiteSnapshot(
        url=url, html=html, css=css,
        title=_strip_tags(title_m.group(1)) if title_m else "",
        meta_description=meta_m.group(1).strip() if meta_m else "",
        hero_text=_strip_tags(h1_m.group(1)) if h1_m else "",
        logo_bytes=logo_bytes, logo_ext=logo_ext,
    )


# ---- CSS extraction --------------------------------------------------------------------

CUSTOM_PROP_HEX_RE = re.compile(r"--[\w-]+\s*:\s*(#[0-9A-Fa-f]{6})\b")
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}{]+)")
GENERIC_FACES = {"sans-serif", "monospace", "serif", "system-ui", "-apple-system", "inherit",
                  "cursive", "fantasy", "ui-sans-serif", "ui-monospace", "arial", "helvetica"}


def extract_colour_frequencies(css: str, cap: int = 6) -> list[str]:
    """Hex colours ranked by frequency, custom-property declarations counted first (T20
    spec) and falling back to any hex literal in the sheet if the site defines none."""
    from collections import Counter
    custom_hits = CUSTOM_PROP_HEX_RE.findall(css)
    counts = Counter(h.upper() for h in custom_hits) if custom_hits else Counter(
        m.group(0).upper() for m in HEX_RE.finditer(css))
    return [h for h, _ in counts.most_common(cap)]


def extract_font_families(css: str, cap: int = 4) -> list[str]:
    seen: list[str] = []
    for m in FONT_FAMILY_RE.finditer(css):
        first = m.group(1).split(",")[0].strip().strip("'\"")
        if first and first.lower() not in GENERIC_FACES and first not in seen:
            seen.append(first)
        if len(seen) >= cap:
            break
    return seen
