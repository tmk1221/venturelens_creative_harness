# Imagery: generated stills and B-roll

One photographic look for everything a model paints. The style block below is appended, verbatim, after the beat's own content in every still prompt; it describes how a picture is rendered and never what is in it, so it cannot contradict a beat. Subject, setting, people, objects and framing are the beat's to decide.

## stills.style_block

> [Under 90 words, cinematographer language, positive phrasing only: light quality and direction, palette in words with no hex, lens and depth of field, texture and grain, the state of the spaces, how people look. No subject, no place, no brand name, no font name.]

Reference images are optional. When a set of eight to fifteen approved stills exists, run `python -m brandkit derive-style <folder> --kit <client>` and replace the block with the accepted draft.

## A menu for whoever writes the beat

Not appended. Terms the models understand, to choose from when a beat needs them:

- **Framing**: wide establishing, medium, close-up, extreme close-up, over-the-shoulder, two-shot.
- **Angle**: eye level by default; high angle for an overview; low angle for scale.
- **Light**: window side light, overcast daylight, a single practical, late-afternoon sun.
- **Camera, video pass only**: locked-off, slow push-in, slow lateral slide, tracking alongside, handheld drift. One move per clip, already in motion at the first frame.
- **Duration**: four to eight seconds.

## Composited, never generated

The mark, screens and any legible text, per the house rule. They are placed from `assets/Logos` and the HyperFrames compositions after the image exists.
