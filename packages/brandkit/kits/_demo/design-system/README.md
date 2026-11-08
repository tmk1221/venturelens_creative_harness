Kestrel Demo Co. keeps the books and runs payroll for small independent shops, for cafés, studios and repair shops that want people, not a portal. It is a made-up company: Post3's demo and test kit. The identity is three discs of falling size, a big steady circle with two smaller ones beside it, the business and the people around it.

## Voice

- Warm, practical, steady, plain-spoken.
- Write to one viewer as *you*. Kestrel Demo Co. is *we*.

## Color

- Three brand colours, in the order the mark uses them: `primary` (forest), `secondary` (sage), `accent` (amber). They are fills; only `primary` is dark enough for text on `surface`.
- `ink` on `surface` or `surface-raised` for all reading text; `muted` for secondary lines. Every pair holds 4.5:1 or better in both themes.
- Amber is the one emphasis colour: one element per frame, never text.
- Video grounds: `ground-light` for light end cards, `ground-dark` (which is `primary`) for dark ones. The mark sits on light grounds as drawn; on `ground-dark` its large disc becomes `on-primary`.

## Logo

The mark is `assets/Logos/mark.svg`. Never redraw it.

| File | Use |
| --- | --- |
| `mark.svg` | On light grounds. |
| `lockup.svg` | Mark plus wordmark for headers and end cards. |

- Clear space is half the mark's height on every side. Minimum size 24px for the mark, 160px wide for the lockup.
- Never rotate, stretch, recolour, or add a shadow, outline or gradient.

## Type

- Manrope is the only typeface, loaded from Google Fonts, weights 400, 500 and 700.
- Scale: `display` 64, `title` 40, `heading` 24, `body` 16, `small` 13, `label` 12.
- Headlines get `text-wrap: balance`; body lines stay near 65 characters.

## Layout and shape

- Circles are the brand shape: pills and dots from `radius-pill`, cards from `radius-md`, the app icon from `radius-tile`.
- Separate surfaces with `line` hairlines. Brand elements carry no shadow.
- Spacing runs 4, 8, 16, 24, 32, 48, 64. On a 1080p frame the title-safe inset is `space-6`.

## Motion

- Two brand animations, each a HyperFrames composition: an end card where the three discs roll in, and a lower third.
- The house ease is `power2.out` for entrances. Durations: 150ms micro, 350ms standard, 700ms slow.
- Live UI only: when a viewer's system has Reduce motion on, skip the animation and show its final frame. Rendered video is unaffected.

## Video templates

- The end card and lower third are components; each component's guideline says what to provide and where it sits.

## Generated imagery

- One photographic look. The style block in the Imagery section is appended verbatim to every still prompt; everything else about a shot is decided at the beat.
- Never ask a model to render the mark, a screen or text. Those are composited from the SVG files and the compositions.

## Iconography

- Lucide icons at 1.75px stroke in `ink` or `muted`. No emoji as icons.
