[Client] is [what they do, in one sentence, present tense], for [who they serve]. The identity is [the mark and the one idea it carries, in one sentence].

## Voice

- [Three to five adjectives, positive only. Who this brand is.]
- Write to one viewer as *you*. [Client] is *we*.

## Color

- [The brand colours in the order the mark uses them, by token name: `primary`, `secondary`, `accent`. Say which are fills and which may carry text.]
- `ink` on `surface` or `surface-raised` for all reading text; `muted` for secondary lines. Keep every pair at 4.5:1 or better in both themes.
- [Emphasis rule: where the accent may appear and how often. One element per frame is a good default.]
- [Grounds for video: which token is the light ground, which the dark, and which mark goes on each.]

## Logo

The mark is `assets/Logos/[mark].svg`, the production file. Never redraw it; every variant is that file recoloured.

| File | Use |
| --- | --- |
| `[mark].svg` | On light grounds. |
| `[mark-dark-ground].svg` | On dark grounds. |
| `[lockup].svg` | Mark plus wordmark for headers and end cards. |

- Clear space is [a fraction of the mark's height] on every side. Minimum size [n]px for the mark, [n]px wide for the lockup.
- Never rotate, stretch, recolour outside the defined variants, or add a shadow, outline or gradient.

## Type

- [Family] is the only typeface, loaded from Google Fonts, weights [400, 500, 700]. [Second family only if the brand truly has one, and what it is for.]
- Scale: `display` [64], `title` [40], `heading` [24], `body` [16], `small` [13], `label` [12].
- Headlines get `text-wrap: balance`; body lines stay near 65 characters.

## Layout and shape

- [The brand's shape language: which radius tokens for which elements.]
- Separate surfaces with `line` hairlines by default. [Say whether brand elements carry shadows; most should not.]
- Spacing runs 4, 8, 16, 24, 32, 48, 64. On a 1080p frame the title-safe inset is `space-6`.

## Motion

- [The brand animations, each a HyperFrames composition in the Motion section. Name them and what each is for.]
- The house ease is `power2.out` for entrances. Durations: 150ms micro, 350ms standard, 700ms slow.
- Live UI only: when a viewer's system has Reduce motion on, skip the animation and show its final frame. Rendered video is unaffected.

## Video templates

- The end card, lower third and any agent or loading state are components; each component's guideline says what to provide and where it sits.

## Generated imagery

- One photographic look. The style block in the Imagery section is appended verbatim to every still prompt; everything else about a shot is decided at the beat.
- Never ask a model to render the mark, a screen or text. Those are composited from the SVG files and the compositions.

## Iconography

- [Icon set, stroke weight, colours.] No emoji as icons.
