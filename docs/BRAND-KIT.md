# Brand kit — one shared core, positive only

`packages/brandkit/` turns a client's brand into what the pipeline actually needs:
purity-checked image/video prompt fragments, a `brand.css`, a `design.md` for
HyperFrames, a `captions.json`, and a QA checklist — never `brand.yaml` parsed ad hoc
somewhere else. Full rationale: `docs/research-brand-consistent-generation.md`.

**T39: a client's kit lives with its company in the media library, `<library>/<Company>/brand/`,
never in this repo** (Post3 finds it there for that company's projects). The repo's `kits/` holds
only `_template` and the neutral `_demo` kit (a made-up company) that tests and demos use.

**T20: the kit is GENERATABLE end to end and POSITIVE ONLY.** `python -m brandkit init
<client> --from <url>` takes a first guess at every field from a live site, marking each
one `guessed: true`. There is no `forbid` key anywhere in a kit — the schema rejects one
with a helpful message. A brand kit describes what the brand IS; any beat may warrant
anything.

## What the kit is NOT

- **Not a character/location bible.** Keeping a recurring presenter or a recurring set
  consistent across a project belongs to that project's cast registry and beat graph —
  not to the brand kit.
- **Not a style-anchor image library.** Reference photos/footage are never attached to a
  generation to copy from directly. Instead, they're raw material: `derive-style` turns
  them into a short written description of what they have in common.

## The layers, merged in order: house → brand → look

1. **`house/house.yaml`** — Travis's universal craft rules, the same for every client:
   prompt template shapes, safe areas, easing/duration defaults, the 60/30/10
   colour-ratio rule, and the QA checklist. `house.never_generate` is a *model-limitation
   default*, not a brand rule (today's image/video models can't reliably render legible
   text, a logo, or a screen with content) — every `still_prompt()` call appends these as
   forced negatives unless the caller's own `slots["allow"]` lifts the matching one
   (`"text"` / `"logo"` / `"screen"`) for that one beat. A kit never overrides this list.
2. **`kits/<client>/brand.yaml`** — one client's real brand, built around a single
   **`core`** (see below) plus `stills`, `video`, and `animation` (behaviour only).
3. **`kits/<client>/looks/<name>.yaml`** (optional, per video or series) — a small,
   narrow override for one video: a different style block, a different accent, a
   different camera feel, or a caption tweak.

## `core` — who the client is, everything the other sections draw on

- **`identity`** — `name`, `what_they_do`, `who_they_serve`. Feeds the writer's context
  (`compile.writer_context`), never pasted into an image prompt.
- **`colours`** — the client's **real** brand colours, 3–6 of them, each keyed by a
  **role**: `primary`, `secondary`, `accent`, `dark_neutral`, `light_neutral`. Each has a
  plain-English name for prompts (`name_plain`) and a hex for HTML/CSS use only, plus
  `world_tone` (`light`/`dark` — which neutral pole the frame reads as) and `dominant`
  (which role covers most of the frame). **UI shades are GENERATED, not hand-picked**:
  `ui_shades.derive_ui_shades(colours, world_tone)` computes a ground, three surface
  tiers, three ink tiers, a hairline, and an accent wash by mixing the kit's own colours
  (plain sRGB lerp, stdlib only), and checks WCAG contrast (ink on every surface ≥
  4.5:1). A kit's `animation.css_vars` may still record an *explicit override* for any
  of those same keys — that's how Acme's existing brand.css values keep rendering
  unchanged even though the shades are now computed rather than typed in.
- **`typography`** — `heading`, `body`, optional `mono`: `family`, `source`
  (`google`/`file`), optional `file`.
- **`logos`** — moved here from `animation` (a logo is a brand asset, not motion
  behaviour). Same slot shape as before: `file`, `clear_space`, `min_size_px`,
  `placements` (16:9 and 9:16 once filled).
- **`personality`** — `is` (3–5 adjectives) and `voice` (one sentence).
- **`world`** — `places`, `people`, `objects`, `textures`: the subject matter that
  belongs in this brand's pictures, **positive only** — name what DOES belong, never
  what to avoid.
- **`names`** — `official`, `products`, `pronunciation`. No `forbid` list: lint now
  **warns** (never fails) when an on-screen name isn't in `official`/`products`, naming
  the unknown name so a human notices.
- **`sources`** — `[{kind: website|style_guide|file, ref, fetched_at}]`, recording where
  a guessed value came from.

## `stills` — the AI-generated-photo problem

- **`style_block`** — the real "look" lever: lens, lighting, colour handling, texture,
  production design, in plain photographic language. **Never hand-write this.** Build it
  from real approved reference images:
  ```
  python -m brandkit derive-style <folder-of-images> --kit <client>   # writes a DRAFT for you to read and edit
  python -m brandkit accept-style <client>                             # promotes the edited draft, bumps its version
  python -m brandkit test-style <client>                               # six prompts for unrelated subjects — run them, eyeball family resemblance
  ```
  A purity check runs on the draft and again on accept: no hex, no quotes, no named
  subject, under a 90-word cap.
- **`accents`** — how brand colour enters a generated scene: a named wardrobe/prop/light
  accent, never an instruction to match a hex.

`still_prompt(slots, kit, look)` combines the style block, accents, and the house
`never_generate` defaults (minus anything a beat's `slots["allow"]` lifted) with the
caller's own content (shot type, subject, action, setting, optional continuity-reference
image paths). **No reference image is attached to the generation itself.**

## `video` — the AI-generated-clip problem

`camera_personality` (the brand's default camera feel) and `pacing_default`.
`motion_prompt(slots, kit, look)` builds camera → subject motion → what stays static →
pacing, and **never restates style, lighting or palette** — the still that starts the
clip is the anchor.
Camera and pacing come from the beat first, then the look, then the kit; when none of
them names one (a Brand System kit leaves both to the beat) the house neutral defaults in
`house.motion_prompt.defaults` apply (a locked-off frame, subtle pacing), so a video beat
never fails for want of a camera.

## `animation` — motion/graphics BEHAVIOUR only

T20 shrank this section to pure behaviour — the tokens it used to hold (`type`, `logos`,
`names`) moved to `core`. What's left: `grid_safe_areas`/`easing`/`durations`/
`colour_ratio` (kit-specific notes on top of house defaults), `caption_style`
(`font_role` now points at a `core.typography` role), `sfx_palette`, and `css_vars`
(explicit UI-shade overrides, or a craft-level token that isn't a real brand colour at
all). `animation_brief(kit)` bundles `core.colours`/`typography`/`logos` plus this
section into JSON for the HyperFrames agent — it is deliberately **not** run through the
purity check the still/motion builders enforce.

## Fillable fields: filled / pending / guessed

Most fields carry `status: filled | pending` and an optional `guessed: true`.

- `status: pending` is a **valid, reportable slot**, not an error. Run
  `python -m brandkit status <kit>` to see every pending field and what it blocks.
- `guessed: true` marks a *filled* field whose value was inferred — by a human's first
  guess or `brandkit init --from` — rather than confirmed against a real brand source.
  Review it before trusting it in production.
- **Never invent a value to make a field look filled.** Leave it `pending`, or fill it
  and mark it `guessed: true`.

## Generating a kit end to end

```
python -m brandkit init <client>                          # copies kits/_template/ to kits/<client>/, all pending
python -m brandkit init <client> --from <url> [--guide g]  # fetches the site and drafts EVERYTHING, all guessed:true
python -m brandkit status <client>                         # readiness report: filled/pending/guessed + what's blocked
python -m brandkit compile <client> <out-dir>              # brand.css, design.md, captions.json, qa_checklist.md, kit.json
python -m brandkit lint <client> <composition-dir>         # does a composition follow the kit? (warns on unknown names, never fails)
python -m brandkit derive-style <folder> --kit <client>    # draft a stills.style_block from reference images
python -m brandkit accept-style <client>                   # promote a reviewed draft, bump its version (comments preserved)
python -m brandkit test-style <client>                     # six family-resemblance prompts, no generation
```

`init --from` fetches one page + its linked CSS (urllib, capped sizes — tests always use
a saved fixture, never the live network), extracts colour frequencies (CSS custom
properties first), font families, the header logo, and title/meta/hero copy
mechanically; a `TextProvider` (same shell-out pattern as `vision.VisionProvider`, and
equally banned from tests) drafts the language fields — identity, personality, world,
names, style_block, accents, camera_personality — from that copy. Every write carries
`guessed: true` and a `core.sources` entry.

`kits/_template/brand.yaml` is annotated: every field is marked REQUIRED or OPTIONAL with
a one-line "how to fill this in" note, written for someone who isn't a designer. It loads
successfully as-is — "incomplete but well-formed" — with everything `pending`. Kit writes
that must preserve those hand-written comments (`init --from`, `accept-style`) go through
`ruamel.yaml`'s round-trip loader/dumper (`yaml_io.py`); nothing else in this package
writes a kit back out.

## One kit per project (T33)

A post3 project names its kit (`Project.brand_kit`, a folder under `kits/`; projects made
before T33 load `acme`). `post project set-kit <kit>` or the shell header's Brand picker
(`PATCH /api/projects/{pid}`) switches it, refusing an unknown kit; `GET /api/brand-kits`
lists each kit with its `status` counts. Switching re-points every workflow at the new kit
(`post_core.recipes.rebrand`: its hash, `kit_dir`, the `Style:` line of still prompts, the
brief writer's context), so branded nodes and everything downstream read **stale**: old
outputs stay visible and nothing regenerates until someone runs it. `post_core.brand` is the
only loader; `$POST3_KITS_DIR` points it at another kits folder (tests use a temp one).

`kits/show/` (Sample Weekly Show) is `init --from https://example.com`, run once:
every filled field is `guessed`, nothing is confirmed until Travis reviews it (H6).

## Overrides

A kit's `house_overrides:` may only touch a house section marked `overridable: true`
(currently `motion_design` and `color_ratio`). Safe areas, the QA checklist,
negative-prompt caps, `never_generate`, and the prompt template structures are fixed
across every client.

A `looks/<name>.yaml` may only override `style_block`, `accents`, `camera_personality`,
and (within `animation`) `caption_style` — nothing else.

## Acme today

`kits/acme/brand.yaml` has real palette hex values and type families sourced from
`~/cc/animator/acme/_brand/brand.css` (see `NOTES.md` alongside it for what's guessed
vs. sourced). Its three real brand colours (`light_neutral` = cream, `dark_neutral` =
charcoal, `accent` = ochre) generate the UI-shade ramp; `animation.css_vars` records
today's exact brand.css hex values as explicit overrides so the rendered look is
unchanged by this rewrite. Both logo slots carry the pre-redraw SVGs (`guessed: true`);
`video` is largely `pending`; `core.world`/`core.personality`/
`core.identity.who_they_serve` are first guesses for T20, marked `guessed: true` —
react to them. The old invented-product-name list that used to fail a lint check lives
on in `NOTES.md` as history only; lint now warns instead.
