# Brand-Consistent AI Generation: Research and Proposal

Research date: 2026-09-21. Compiled for the Post pipeline (LLM prompt writer → Higgsfield Nano Banana / Nano Banana Pro stills → Kling 3.0 / Veo 3.1 image-to-video → HTML/HyperFrames motion graphics → DaVinci Resolve). Focus: Acme (B2B IT client) and the general case of running multiple client "brand kits" through one pipeline without over-engineering.

Claims are drawn from vendor docs, practitioner blogs, and design-system references current as of September 2026. Single-blog-sourced claims are marked **[unverified]**.

---

## 1. Consistent, distinct style across many stills

**Reference images beat prose, everywhere.** Google's own guidance, Midjourney's docs, Higgsfield's blog, and independent brand-consistency writeups all converge: a picture of the style works; a description of it degrades. One source states it plainly — hex codes, font names and clear-space rules "degrade the moment they hit a diffusion model. It approximates colour through language, not code" ([Sameness](https://www.sameness.co/blog/brand-consistent-ai-image-generation); [Leonardo](https://leonardo.ai/news/maintaining-brand-consistency-in-ai-images-and-videos); [Typeface](https://www.typeface.ai/blog/ai-brand-management-how-to-maintain-brand-consistency-with-ai-image-generators)). Where prose is unavoidable (mood, texture), evocative language beats technical language: "deep British racing green" activates learned associations; `#184F35` does not. **[unverified — no source benchmarks hex adherence directly, but all agree it's poor]**

**Style bibles.** No canonical "AI style bible" case study was found; the space is ad hoc in 2026. The recurring pattern in practitioner tooling (e.g. the "StyleRef" concept) is to store the style as a structured spec once and translate it per tool — keywords + `--sref` for Midjourney, prose for Flux, labeled sections for DALL-E — rather than one prose paragraph pasted everywhere ([Prompt Architects](https://prompt-architects.com/blog/214-style-references-in-midjourney-sref-explained); [styleref.io](https://styleref.io/blog/midjourney-style-reference)).

**Structured/JSON prompting for Nano Banana and Gemini.** Google's own developer blog and Cloud Blog both prescribe a *prose* structure: subject + action + setting + style/medium + lighting + camera/composition + aspect ratio, written as full sentences like a cinematographer's shot list, not keyword lists ([Developers Blog](https://developers.googleblog.com/how-to-prompt-gemini-2-5-flash-image-generation-for-the-best-results/); [Cloud Blog — Nano Banana](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana); [Cloud — best practices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-image-generation-best-practices)). Nano Banana Pro specifically reasons through a scene ("Deep Think") before rendering, and is unusually good at structured on-image content like charts and legible text when explicitly asked for it. JSON-style prompting (fields for subject/camera/lighting/materials/composition/negative/output) is a **community practice, not a Google recommendation** — useful for programmatic pipelines that assemble prompts from templates, but not shown to out-perform prose. Treat it as "convenient for automation," not "better images." **[unverified as qualitatively superior]** ([Miraflow](https://miraflow.ai/blog/nano-banana-json-prompting-2026); [gemini-image-prompting-handbook](https://github.com/pauhu/gemini-image-prompting-handbook)).

**Photographic language** is the highest-leverage, lowest-risk lever for "look": lens choice, aperture/depth of field, camera angle, lighting direction, time of day, film-stock/grain. "Using terms like 85mm lens or shallow depth of field improves realism" ([Cloud Blog](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana)). This is the mechanism Post should lean on for distinct style, not colour codes.

**Palette without hex codes:** put brand colour into things in the scene — wardrobe, props, accent lighting, a painted wall — not as an instruction. "Uploading a color palette... or your official logo... guide[s] the AI to use your exact visual assets instead of guessing from text" ([Typeface](https://www.typeface.ai/blog/ai-brand-management-how-to-maintain-brand-consistency-with-ai-image-generators)). For Acme: brand blue on a jacket lining or monitor-bezel accent, never a prompt clause.

**Character/location consistency:** the converging recommendation across five sources is to build one canonical reference sheet (multiple angles/poses) once, and re-attach that same image to every new generation. **Do not chain** (feeding generation N's output as N+1's reference) — chaining causes identity drift: "generate one canonical character sheet and reference that file every single time rather than the last image you made" ([ModernPhotoTools](https://modernphototools.com/blog/maintain-character-consistency-in-ai-image-generation); [GensGPT](https://www.gensgpt.com/blog/consistent-characters-across-multiple-images-maintain-identity-style-accuracy-2026-guide)).

**Seeds:** not addressed in depth for Nano Banana/Higgsfield specifically; a Stable-Diffusion-era lever that matters less on reference-image-driven multimodal models, where the reference image does the consistency work a seed used to do. Treat as minor/optional. **[unverified for these specific models]**

**Midjourney `--sref` / Flux LoRA / Higgsfield Soul ID — worth it?**
- `--sref` transfers "colors, medium, texture, lighting — but not subjects" from a reference image or code ([Midjourney docs](https://docs.midjourney.com/hc/en-us/articles/32180011136653-Style-Reference)). Midjourney-only, but confirms the general principle Post should replicate manually with style-reference stills.
- Flux LoRA style training is worth it only for high-volume ongoing work with one visual system; for occasional projects, "prompt + reference image usually gets you there without any training run" ([Prompt Architects](https://prompt-architects.com/blog/596-loras-and-style-consistency-what-prompts-cant-do-alone); [The Neural Base](https://theneuralbase.com/flux/learn/advanced/subject-vs-style-training/)). **Recommendation: skip LoRA for now** — one client at modest volume doesn't clear the bar; revisit only if Post scales to many daily-output clients.
- Higgsfield Soul ID is a trained identity embedding (20–80 photos, ~3–5 min) that keeps a *person's* face/body consistent across 20+ curated aesthetic presets ([Higgsfield](https://higgsfield.ai/blog/SOUL-ID-Superior-Level-of-AI-Character-Consistency)). Worth adopting only if a recurring on-camera generated presenter/avatar is needed — not for baseline style consistency.
- Krea/Freepik presets are functionally equivalent curated anchors; not a differentiator without a reference image underneath.

**What does NOT work:** hex codes, exact font names, brand words/taglines expected as clean typography, quoted text generally (models render text unreliably and literally — this is Post's known failure mode), and long negative-prompt lists that dilute each term ("a focused list of five to eight... will outperform a kitchen-sink list of forty" — [Cliprise](https://www.cliprise.app/learn/guides/best-practices/negative-prompts-guide-fixing-common-ai-generation-mistakes)). A titled "HOUSE LOOK" block pasted into an image prompt is the direct cause of Post's literal-signage failure: the model treats brand prose as content to render, not as a style instruction.

---

## 2. How brand enters generated live-action imagery legitimately

1. **Product/logo as a reference image**, never a text description.
2. **Environment dressing** — brand colour as an accent (jacket, mug, monitor bezel), never a global instruction, never legible signage.
3. **Never generate a screen.** "Generate the scene without asking the model to redraw the mark, then place the approved vector or high-resolution logo in post-production" ([LeftHD](https://lefthd.com/insights/keep-logo-accurate-in-ai-generated-images/)). Any screen/monitor/UI surface should be generated blank/dark, with the real logo/UI composited in Resolve or the HTML/HyperFrames overlay layer Post already uses for motion graphics.
4. Re-anchor composited logos per aspect ratio, roughly 5–10% of frame width as a scaling target. **[unverified — general convention, not a cited brand standard]**

**Rule for Post:** any pixel that needs to be a legible brand asset — logo, wordmark, UI, chart, lower-third text — is never requested from the image/video model. It is always an HTML/HyperFrames composite or Resolve overlay. This is already Post's motion-graphics architecture; the fix is applying it to B-roll too.

---

## 3. Image-to-video: Kling 3.0, Veo 3.1, general practice

**Kling 3.0:** converges on a 5-part motion-prompt structure — subject details, motion specification, camera work, environment, style/lighting. "Treat the input image as an anchor... Kling 3.0 excels at preserving the identity, layout, and text details of the source image while introducing motion and depth" — the motion prompt should describe only the delta, leading with camera language. Kling exposes motion intensity (0.3 subtle → 1.0 dramatic) and multi-shot mode with an "element reference" system for cross-shot character consistency ([fal.ai](https://blog.fal.ai/kling-3-0-prompting-guide/); [Morphic](https://morphic.com/resources/how-to/kling-3.0-guide)).

**Veo 3.1:** near-identical 5-part structure — shot composition, subject/action, environment, camera movement, style/mood — "lead with camera" ([Cloud Blog](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3.1); [Sider](https://sider.ai/blog/ai-tools/best-prompt-techniques-for-veo-3_1-video-output-a-field-guide-to-cinematic-control)). Responds to full "director's treatment" prompts: shot size, lens, move, blocking, lighting, sound.

**A motion prompt should contain:** camera move first (dolly/pan/track/static/handheld); subject motion (what, how fast); explicitly named static elements (reduces unwanted drift); pacing/intensity; and nothing else — "your prompt is not there to repeat what the pictures already show... it's there to describe the motion between them" ([Dojoclip](https://dojoclip.com/en/blogs/how-to-use/write-better-video-prompts-start-end-frames)).

**Style stays locked by the start frame.** Re-stating style/lighting/palette in the motion prompt risks the model drifting the look while satisfying new text; keep motion prompts short and single-purpose.

**End-frame use:** first/last-frame mode lets the model "intelligently animate the in-between" — useful for a controlled reveal (product/logo handoff) at some cost to directorial control over *how* it gets there ([Artlist](https://artlist.io/blog/ai-video-start-and-end-frame/)). Use selectively for shots where the final composition matters (e.g. landing clean for an overlay handoff), not as a default.

**Common artifacts:** motion blur, face distortion, warping, duplicate limbs, background drift, floating objects, flicker/ghosting. Negative prompts should be **short and targeted** (5–8 terms beats 40) and work for a stray object or unwanted overlay-like text, but are **not reliable** for timing errors, identity drift, or traits inherited from the reference image — those need fixing at the still stage ([Cliprise](https://www.cliprise.app/learn/guides/best-practices/negative-prompts-guide-fixing-common-ai-generation-mistakes)).

**Duration/handles:** typical range 4–12s; longer feels smoother but slower, shorter punchier but rougher. The strongest recurring craft advice: describe **one action**, not a sequence — multi-action prompts reliably compress, skip, or garble. This maps naturally onto Post's need: each B-roll clip is a single beat.

---

## 4. How agencies operationalize this, 2025–2026

This is the thinnest-evidenced section — searches mostly surfaced generic AI-design-tool marketing, not named case studies. No documented "how [major agency] does AI brand look-dev" writeup was found. What recurs in aggregate:

- **Look-dev / reference-set phase:** a small set of approved "hero" stills is produced and hand-picked to define the visual system, then reused as the style-reference input for every later generation — the practical form of "style bible as images" from §1. **[unverified as a named industry-standard practice — it's the converging logic, not a single case study]**
- **Prompt templates with slots:** sources reference structured briefs (audience, emotion, brand constraints, content hierarchy, examples to avoid) as the standard input shape before the prompt itself is written ([Hyperfx](https://www.hyperfx.ai/blog/design-resources-for-websites-and-ads-2026)).
- **QA:** no named commercial tool does OCR-for-stray-text or CLIP/DINO brand-similarity scoring as a documented product. Academic sources describe VLM-as-judge (0–5 rubric scoring) and CLIP-embedding distance as generic techniques ([TypeScore](https://arxiv.org/pdf/2411.02437); [VLM survey](https://openreview.net/pdf?id=ThjDCZOljE)), but nothing ties these specifically to brand QA at agency scale. **Treat this as DIY-able** — OCR on stills to flag stray text, a VLM scored against a written rubric, CLIP cosine-distance to the approved hero-frame set — rather than something to buy off-the-shelf. **[unverified — no turnkey product found]**

**Takeaway:** the agency-process layer is less mature/documented than model-level prompting guidance. Post doesn't need to reverse-engineer a named workflow; the converged best practice (reference-driven look-dev, slot-based templates, lightweight QA) is simple enough to build directly (§6).

---

## 5. Motion graphics brand systems

- **Easing:** IBM Carbon defines "productive" (fast) vs "expressive" (slower, more character) motion, each with standard/entrance/exit curves exposed as reusable tokens rather than one-off choices ([Carbon](https://carbondesignsystem.com/elements/motion/overview/)). Material Design 3 defines standard/decelerate(entrance)/accelerate(exit) curves; "motion appears more natural... when acceleration and deceleration occur asymmetrically" ([Material 3](https://m3.material.io/styles/motion/easing-and-duration)).
- **Duration:** non-linear, driven by distance/size of the change, not a flat constant — larger changes take longer (Carbon); "fast enough not to cause waiting, slow enough to be understood" (Material, Shopify Polaris state this near-identically) ([Polaris](https://polaris-react.shopify.com/design/motion/using-motion)).
- **Entrance/exit grammar:** Material and Carbon both use different easing for elements coming in vs. going out; Polaris frames "snappiness" (fast start, decelerate) as the default feel.
- **Grid/safe areas per aspect ratio:** Henkel's public guide specifies a literal grid (9:16: 12 columns, action-safe zone = 2 building modules) with logo animation confined to that zone, anchored bottom/top-right ([Henkel](https://www.henkel-brand-hub.com/brand-design/Motion.html)). HBO Max requires top/bottom graphics to auto-reposition into platform-specific safe areas ([HBO Max](https://brand.hbomax.com/motion)). Generic broadcast convention: action-safe ≈90%, title-safe ≈80% of frame.
- **Colour ratio:** 60/30/10 (dominant/secondary/accent) is the standard convention for balancing brand colour without exhausting the eye or losing the accent's power to direct attention ([Wix](https://www.wix.com/wixel/resources/60-30-10-color-rule)).
- **Max simultaneous moves / caption style / SFX:** no public guideline found specifying numeric limits; treat as house-craft judgment, not a documented external standard. **[gap]**

**Design tokens:** the W3C Design Tokens Community Group shipped its first stable spec, version 2025.10, on 2025-10-28 — JSON format (`.tokens`/`.tokens.json`), each token carrying `$value`, `$type`, optional `$description`, backed by 40+ orgs including Adobe, Figma, Google, Shopify ([W3C DTCG](https://www.w3.org/community/design-tokens/2025/10/28/design-tokens-specification-reaches-first-stable-version/)). Style Dictionary v4 has first-class DTCG support; full 2025.10 support is still landing in v5 ([Style Dictionary](https://styledictionary.com/info/dtcg/)). A flat YAML kit capturing the same conceptual fields is right-sized for Post today; adopting the full W3C token format now would be over-engineering for one client, with a clear upgrade path later.

**Universal ("house craft") vs. brand-specific:**

| Universal | Brand-specific |
|---|---|
| Non-linear duration scale (distance/size-driven) | Exact duration numbers per element |
| Asymmetric easing (decelerate in / accelerate out) | Exact cubic-bezier "personality" |
| Action-safe 90% / title-safe 80% | Exact logo anchor position |
| 60/30/10 colour ratio as a rule | Which colours fill each role |
| Motion has clear purpose, not decoration | Caption style, SFX palette, entrance/exit grammar specifics |

---

## 6. Concrete proposal

### (a) Universal vs. brand-specific vs. per-video

| Layer | UNIVERSAL (every client) | BRAND-SPECIFIC (per kit) | PER-VIDEO |
|---|---|---|---|
| **Stills** | Narrative prompt structure (subject/action/setting/composition/lens/lighting/mood); photographic vocabulary; no hex/fonts/quoted text ever; reference-sheet-not-chaining discipline; negatives ≤8 terms | Hero-frame style references; brand colour as wardrobe/prop/lighting accents; approved logo/product reference images; recurring character (Soul ID) if applicable | Episode setting, wardrobe variant, season mood |
| **Video** | 5-part motion structure (camera→subject motion→statics→pacing, no restated style); single-action prompts; start-frame-as-style-anchor; negatives only for observed failures | Brand-typical camera personality; default motion intensity | Beat-specific camera move; end-frame for a scripted reveal |
| **Motion graphics** | Non-linear duration; asymmetric easing; action-safe 90%/title-safe 80%; 60/30/10 discipline; never generate a screen — all logos/UI/text are HTML/HyperFrames composites | Actual brand colours, logo file + clear space, type family/scale, caption style, SFX palette, entrance/exit grammar | Lower-third copy, chart data, per-episode title content |

### (b) Minimum-viable brand kit skeleton

```yaml
# brand-kit.yaml — one file per client. Required = must be filled before use.
brand:
  name: "Acme"                       # required — filenames/folders only
  industry: "B2B IT services"           # required — one line; informs wardrobe/prop choices

palette:                                 # required
  # Fill: pick 3 colours off the real logo/website, name them in plain
  # English (that name goes in prompts). Hex is only for HTML overlays,
  # never image/video prompts.
  primary:   { name: "Acme blue",  hex: "#0B4F9E" }
  secondary: { name: "warm graphite", hex: "#2B2B2E" }
  accent:    { name: "signal amber",  hex: "#F2A93B" }
  ratio: "60/30/10"                      # optional — override only if documented differently

typography:                              # required for motion graphics only
  heading_font: "Inter Bold"             # required — a real installed family
  body_font: "Inter Regular"             # required — never put a font name in an image/video prompt

logo:                                    # required
  file: "references/logo-primary.svg"    # required — vector preferred
  clear_space: "1x logo height on all sides"   # optional, default if unsure
  placement_default: "top-right, ~7% of frame width"  # optional
  rule: "Never generate a logo. Always composite this file in HTML/Resolve."  # fixed

voice_and_mood:                          # required — feeds the prompt "mood" slot
  description: >
    Confident, calm, competent. Enterprise-trustworthy, not startup-hype.
    Muted, controlled lighting; nothing neon.
  # Fill: describe the feeling a viewer should have, 2-3 sentences, like
  # describing a person's personality.

visual_style:                            # required — the real "look" lever
  lens_and_camera: "35-50mm equivalent, shallow depth of field, slight low angle"
  lighting: "soft key light, cool-neutral temperature, minimal hard shadow"
  time_of_day: "overcast daylight or clean interior office light — avoid golden hour"
  film_stock_or_grade: "clean digital, slight desaturation, no heavy grain"
  # Fill: brief it like a DP. If unsure, point at 2-3 reference stills and
  # describe what's true of all of them.

wardrobe_and_props:                      # optional, recommended — how brand colour enters scenes
  notes: >
    Brand blue/amber may appear as accents: jacket lining, mug, LED strip,
    monitor bezel. Never a dominant block, never legible brand text.

negatives:                               # optional — only add terms you've actually seen fail
  stills: ["no visible text", "no logos", "no illegible signage", "no distorted hands"]
  video:  ["no flicker", "no warping", "no duplicate limbs"]

references/                              # required folder — see spec below
  hero_frames: ["references/hero-01.jpg", "references/hero-02.jpg", "references/hero-03.jpg"]
  character_sheet: "references/presenter-sheet.jpg"   # optional — only if a recurring presenter/avatar exists
  location_sheets: []                     # optional — one per recurring set

motion_graphics:                         # required for the HyperFrames/overlay layer
  duration_scale: "non-linear, ~200-400ms per UI-scale move"   # optional, default to house craft
  easing: "decelerate on entrance, accelerate on exit"           # optional, default to house craft
  safe_areas: "title-safe 80%, action-safe 90%"                  # optional, default to house craft
  caption_style: "lower-third, brand primary background, heading_font, 2-line max"  # required if captions used
```

**`references/` folder spec:** 3–5 hero frames minimum — final, approved stills attached as style-reference images to every future still generation (more than ~5 dilutes anchor signal). Cover: (1) a clean environment/establishing shot, (2) a close-up product/detail shot, (3) a human-presence shot — same lighting/lens/grade across all. One character sheet (3–4 angles) only if a recurring generated presenter/avatar exists; skip if all A-roll is real footage. Location sheets optional, only for a recurring generated set.

### (c) Prompt templates

**Still-prompt template:**
```
[SHOT TYPE] of [SUBJECT] [ACTION] in [SETTING from visual_style + wardrobe_and_props].
Shot on [lens_and_camera]. [lighting]. [time_of_day]. [film_stock_or_grade].
Mood: [voice_and_mood, condensed to a phrase].
[Optional: brand colour on a named wardrobe/prop item]
Negative: [negatives.stills, 4-8 terms max].
Style reference image attached: references/hero-0X.jpg
[If recurring subject: character/location reference image attached]
```
Deliberately excluded, always: hex codes, font names, brand name/wordmark as text, any "logo" or "screen" instruction, "brand guidelines," any quoted on-screen text.

**Motion-prompt template:**
```
Camera: [single move — dolly in / static locked-off / slow pan / handheld drift].
Subject motion: [one action only — what moves, how fast].
Static: [what should NOT move — named explicitly].
Pacing: [subtle / moderate / dramatic, or numeric intensity].
Negative: [negatives.video, 3-6 terms max].
```
Deliberately excluded: restated style/lighting/palette (locked by the start frame), multi-action sequences, any text/logo instruction.

### (d) 10-item QA checklist

1. No stray legible text anywhere in the frame (eye scan or OCR pass) — highest-value check given Post's known failure mode.
2. No generated logo or screen content — any screen/UI surface is blank/dark or composited in post.
3. Hero-frame family resemblance — lens character, lighting, grade match the approved set (eyeball at current scale; CLIP-distance is future automation).
4. Brand colour present only as accent, never a dominant wash or claimed hex match.
5. No hand/limb distortion on any human subject.
6. Motion matches the single stated action — no drift, no identity/face drift from the start frame.
7. Safe areas respected in any overlay — nothing critical outside the 80% title-safe box.
8. Colour ratio sanity check on composited graphics — brand hue reads as accent, not wallpaper.
9. Captions/lower-thirds use the kit's type family and caption style, not a system default.
10. Character/location consistency across a sequence — regenerated from the canonical reference sheet each time, not chained from a prior output.

---

## Sources

- [Google Developers Blog — Prompting Gemini 2.5 Flash Image](https://developers.googleblog.com/how-to-prompt-gemini-2-5-flash-image-generation-for-the-best-results/)
- [Google Cloud Blog — Ultimate prompting guide for Nano Banana](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana)
- [Google Cloud Blog — Ultimate prompting guide for Veo 3.1](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3.1)
- [Google Cloud — Gemini image generation best practices](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-image-generation-best-practices)
- [Miraflow — Nano Banana JSON Prompting 2026](https://miraflow.ai/blog/nano-banana-json-prompting-2026)
- [pauhu/gemini-image-prompting-handbook (GitHub)](https://github.com/pauhu/gemini-image-prompting-handbook)
- [Midjourney Docs — Style Reference](https://docs.midjourney.com/hc/en-us/articles/32180011136653-Style-Reference)
- [Prompt Architects — Midjourney --sref Explained](https://prompt-architects.com/blog/214-style-references-in-midjourney-sref-explained)
- [Prompt Architects — LoRAs and Style Consistency](https://prompt-architects.com/blog/596-loras-and-style-consistency-what-prompts-cant-do-alone)
- [The Neural Base — Subject vs style training (Flux)](https://theneuralbase.com/flux/learn/advanced/subject-vs-style-training/)
- [Higgsfield — Soul ID: Superior Level of AI Character Consistency](https://higgsfield.ai/blog/SOUL-ID-Superior-Level-of-AI-Character-Consistency)
- [Sameness — How to Build Brand-Consistent AI Image Generation](https://www.sameness.co/blog/brand-consistent-ai-image-generation)
- [Leonardo.Ai — Maintaining Consistent Branding in AI Images & Video](https://leonardo.ai/news/maintaining-brand-consistency-in-ai-images-and-videos)
- [Typeface — AI Brand Management](https://www.typeface.ai/blog/ai-brand-management-how-to-maintain-brand-consistency-with-ai-image-generators)
- [LeftHD — Keep Your Logo Accurate in AI-Generated Images](https://lefthd.com/insights/keep-logo-accurate-in-ai-generated-images/)
- [fal.ai Blog — Kling 3.0 Prompting Guide](https://blog.fal.ai/kling-3-0-prompting-guide/)
- [Morphic — Kling 3.0 Guide](https://morphic.com/resources/how-to/kling-3.0-guide)
- [Sider — Best Prompt Techniques for Veo 3.1](https://sider.ai/blog/ai-tools/best-prompt-techniques-for-veo-3_1-video-output-a-field-guide-to-cinematic-control)
- [Artlist — AI Video Start and End Frame](https://artlist.io/blog/ai-video-start-and-end-frame/)
- [Dojoclip — Write Better Prompts for AI Video with Start + End Frames](https://dojoclip.com/en/blogs/how-to-use/write-better-video-prompts-start-end-frames)
- [Cliprise — Negative Prompts Guide](https://www.cliprise.app/learn/guides/best-practices/negative-prompts-guide-fixing-common-ai-generation-mistakes)
- [ModernPhotoTools — Maintain Character Consistency in AI Image Generation](https://modernphototools.com/blog/maintain-character-consistency-in-ai-image-generation)
- [GensGPT — Consistent Characters Across Multiple Images](https://www.gensgpt.com/blog/consistent-characters-across-multiple-images-maintain-identity-style-accuracy-2026-guide)
- [Carbon Design System — Motion](https://carbondesignsystem.com/elements/motion/overview/)
- [Material Design 3 — Easing and duration](https://m3.material.io/styles/motion/easing-and-duration)
- [Shopify Polaris — Using Motion](https://polaris-react.shopify.com/design/motion/using-motion)
- [Henkel Brand Hub — Motion](https://www.henkel-brand-hub.com/brand-design/Motion.html)
- [HBO Max Brand — Motion](https://brand.hbomax.com/motion)
- [W3C Design Tokens Community Group — Spec reaches first stable version](https://www.w3.org/community/design-tokens/2025/10/28/design-tokens-specification-reaches-first-stable-version/)
- [Style Dictionary — DTCG support](https://styledictionary.com/info/dtcg/)
- [Wix — What Is the 60-30-10 Color Rule?](https://www.wix.com/wixel/resources/60-30-10-color-rule)
- [arXiv — TypeScore: A Text Fidelity Metric](https://arxiv.org/pdf/2411.02437)
- [OpenReview — A Survey on Bridging VLMs and Synthetic Data](https://openreview.net/pdf?id=ThjDCZOljE)
