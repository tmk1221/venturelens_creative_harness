# Motion, regenerated with HyperFrames

Every brand animation is a HyperFrames composition, not a video file. Resolution and frame rate are not part of the design: every size inside a composition is a fraction of the frame, so the same file renders at HD, 4K or any frame rate the timeline uses. Only the aspect ratio is fixed. The complete compositions are files in the Motion asset group.

| Composition | File | Aspect | Length | Output |
| --- | --- | --- | --- | --- |
| [End card] | `assets/Motion/end-card.html` | 16:9 | [4.5s] | opaque MP4 |
| [Lower third] | `assets/Motion/lower-third.html` | 16:9 | [4.0s] | WebM with alpha |

## Regenerating one

1. Copy the file into an empty folder as `index.html`, with the mark beside it under `assets/`.
2. Set the variables at the top of the file: `data-ground` on `<html>` (`light` or `dark`), and any text.
3. Set `data-width` and `data-height` to the Resolve timeline's resolution and render at its frame rate. Every size inside is a fraction of the frame width.
4. Run `hyperframes check .` then `hyperframes render .`, adding `--transparent` for overlays.

## For a new composition

- Build the mark from live elements, never from a flattened image, so it can move. Copy the ground and colour variables from an existing file.
- Set the ground once with `data-ground`; it picks the colours. Never mix a dark ramp with a light ground.
- Keep it seek-safe: one paused GSAP timeline on `window.__timelines.main`, every position a function of progress. Any single frame must render alone.
