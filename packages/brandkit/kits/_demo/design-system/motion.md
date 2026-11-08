# Motion, regenerated with HyperFrames

Every brand animation is a HyperFrames composition, not a video file. Resolution and frame rate are not part of the design: every size inside a composition is a fraction of the frame, so the same file renders at HD, 4K or any frame rate the timeline uses. Only the aspect ratio is fixed. This demo kit ships the descriptions only; the compositions are made per project.

| Composition | Aspect | Length | Output |
| --- | --- | --- | --- |
| End card: the three discs roll in, then the wordmark | 16:9 | 4.0s | opaque MP4 |
| Lower third: an amber dot, then name and role | 16:9 | 4.0s | WebM with alpha |

## For a new composition

- Build the mark from three live circles, never from the SVG, so each disc can move.
- Set the ground once with `data-ground` (`light` or `dark`); it picks the colours.
- Keep it seek-safe: one paused GSAP timeline on `window.__timelines.main`, every position a function of progress. Any single frame must render alone.
