# Port audit: old app (production `post`) vs v3 (`post3`)

Read-only, 2026-09-22. Old app = `~/cc/post` @ `2c07853` + uncommitted `TODO.md`/`board_attention.py`/`story_board.py`. v3 = `~/cc/post3`, tasks T01–T30 per `docs/TASKS.md`. Old-app line numbers per `~/cc/vl/brain/projects/post-v3-audit-current-app.md` §1; not re-verified line-by-line here.

| Capability | Old app has it | v3 has it | Status | Note |
|---|---|---|---|---|
| Medium taxonomy (aroll/provided/video/anim) | `story_board.py:47-55,592-688` | `recipes/templates/{live_action,motion_graphic,provided,overlay}.json`, `RECIPE_KINDS` (`web/src/enrich/CardBody.tsx:10`) | ported | 4 recipe kinds ≈ old medium set; node-graph, not a beat field |
| Overlay depth/position rules | `story_board.py:48-55` (torso-covers-bottom-middle presets) | none found | missing | T30 scope: "depth/position matrix" — still `todo` |
| Start frames ×3 | `story_board.py:1235` `STILLS_PER_BEAT=3` | `instantiate.py:57` `variants: int = 3`, `CardBody.tsx:212-246` variant grid | ported | |
| "+3 more" (extra variant batch) | `story_board.py:750-820` | none found | missing | Generate is a one-shot fixed-count plan; no incremental batch |
| Chained frames (`tree: edit:B03`) | `story_board.py:1238-1247` | none found | missing | No node dependency lets one beat's frame seed another's continuity beyond `still.generate`'s own `continuity` input (same-node, not cross-beat) |
| End frames (from start / describe / sketch) | `story_board.py:823-853` | `node_types.py` `ENDFRAME_GENERATE`/`EndframeGenerateParams` (node type exists) | partial | Node type defined but not wired into `live_action.json` recipe or `CardBody.tsx`; no mode selector, no manual gate |
| Motion rewritten from picked frame | `story_board.py:856-864` | `MOTION_FROM_FRAME` node, wired after `human.pick` (`instantiate.py`), `CardBody.tsx:248-252` shows prompt | ported | |
| Video only from picked frame, backend-enforced | `story_board.py:117-125,867-893` | `VIDEO_GENERATE` requires `start_image` input from pick edge (`node_types.py`); graph readiness enforces order | ported | Dedupe/in-flight check not separately verified |
| Behind-subject measure/cutout/composite preview | `story_board.py:128-138,281-302,1198-1213` | `overlay.json` recipe: measure→cutout→verify→approve; `OVERLAY_MEASURE`/`OVERLAY_CUTOUT` node types, workers exist | partial | Graph skeleton and workers present; no composite-preview UI, no depth/position matrix (see above); recipe not reachable from `CardBody.tsx`'s `RECIPE_KINDS` handling beyond generic card |
| Provided-clip catalogue + assign | `story_board.py:1357-1425` | `PROVIDED_CLIP` node type + `provided.json` recipe, `recipes/workers/provided_clip.py` | partial | Registers one path per node; no folder catalogue/browse/exclude UI found in `web/src` |
| Recurring characters + reference images | `story_board.py:1568-1659` | `recipes/cast.py` (`CastEntry`, `anchor_ready`, approval-gated anchor), `model/cast.py` | ported | Wired into `still.generate` continuity via `instantiate.py`; no cast-management UI found |
| Brand refs (DESIGN.md, logos/UI assets) | `project_brief.py:72-99,266-298`, `FE/Brand.jsx`; lived outside project (`~/cc/animator/<client>`) | `packages/brandkit/kits/acme/{brand.yaml,assets,NOTES.md}`; T01/T16/T17/T20 (all `done`) | ported | Deliberate redesign: compiled `brand.yaml` + lint, versioned kit, in-repo — supersedes old ad hoc `LOOK` string per T01 |
| Plan versions / story lock | `story_board.py:1662-1734` | none found | missing | Brain doc calls this REDESIGN via cuts/variants; not yet built — no versions/locks model in `packages/post_core/post_core/model/` |
| Re-prompt vs re-plan | `story_board.py:720-746,1555-1565` | `BriefEditor` in `CardBody.tsx:303-321` patches `prompt_text`; no separate "re-plan whole beat" op | partial | Editing one field ported; density-slider/re-plan-all concept dropped |
| Note + regenerate | `story_board.py:691-713,896-921` | `CardBody.tsx:181-191,272-285` `onRegenerate`, requires non-empty note | ported | |
| Draft → approve → render (animations) | `story_board.py:1049-1056` | `ANIMATION_DRAFT_RENDER` + `ANIMATION_RENDER` node types, `motion_graphic.json` recipe (`approve_draft`, `approve_final` gates) | ported | Backend graph only; no card UI observed rendering the two-approval flow (CardBody is written for the live_action shape: pick/video/approve) |
| Live HyperFrames studio per beat | `story_board.py:1100-1231` | `recipes/workers/hyperframes_cli.py`, `animation_design.py` | partial | Worker wraps the CLI; no live-preview iframe/studio UI found in `web/src` |
| Render approvals keyed to file (size+mtime) | `board_attention.py:16-180` | `graph/approvals.py` — approvals keyed to **content hash**, ledger + revocation set | ported (redesigned) | Deliberate improvement: hash survives copy/rename, unlike old mtime identity (brain doc §3.6 flags mtime as a weakness) |
| "What needs you" rows + counts | `board_attention.py:183-396`, `Attention.jsx` | `JobsDrawer.tsx:13,31-35` `needsYouCount` badge only | partial | Counter ported; no per-item decision rows/owner model, no project-wide attention page |
| Generate checklist w/ credit count | `story_board.py:1255-1353` | `CardBody.tsx:218-234` plan→"Estimated cost: N credits"→Confirm | ported | Single-node-type checklist (stills); old app's multi-item checklist not reproduced, but the cost-gate pattern is |
| In-app playback incl. alpha | `story_board.py:225-240,443-495` (qtrle+alpha over checkerboard) | `CardBody.tsx:334-339` `<video>` element, no alpha handling | partial | Plain `<video>`; no checkerboard/alpha transcode found |
| Place/placement records | `story_board.py:1429-1552`, `S/resolve-place/scripts/place.py` | `post_core/export/otio_export.py`, `_clips.py`, `_tracks.py` (T09) | partial (redesigned) | v3 exports Cut→OTIO for Resolve import instead of scripting live placement; no placement-record/approval-gated "Place all ready" found; H1 ("Resolve spike: import .otio, report what survives") is still human/open |
| Project brief PROJECT.md | `project_brief.py`, `FE/About.jsx` | none found | missing | No brief model, drafter, or UI in `packages/` or `web/src` |
| Terminal-agent config (Codex/Claude per op) | `B/agents.py`, `docs/terminal-agents.md`, `FE/AgentSetup.jsx` | `post_core/agents/` (`ask_json`, `.post3/agents.json`), `docs/terminal-agents.md` (T36) | partial | Suggest visuals, `brief.write`, `motion.from_frame` call the agent in real mode; provider/model per operation is a JSON file, no setup UI |
| Jobs drawer w/ prompt + progress | `B/jobs.py`, `FE/JobProgress.jsx` (live SSE, prompt text, i/n, pause/cancel/clear) | `web/src/shell/JobsDrawer.tsx`, `post_api/routes/events.py`, `store/jobsStore.ts` | partial | SSE wiring, job kind, %, $ cost ported; no prompt text shown, no pause/cancel/clear buttons found in `JobsDrawer.tsx` |

## Missing, worth porting (priority order)

1. **Project brief (PROJECT.md equivalent)** — old app's single highest-leverage onboarding artifact; nothing in v3 drafts or holds project context for the planner. No task currently owns this.
2. **Behind-subject overlay depth/position + composite preview** — recipe skeleton exists (measure/cutout/verify/approve) but the matrix and preview UI are T30, still `todo`.
3. **"What needs you" project-wide attention view** — only a job counter exists; the old decision-row model (owner you/pipeline, per-beat) is gone. Needed once more than one recipe kind is live at once.
4. **Provided-clip catalogue/assign UI** — node type exists but no folder browse/exclude/assign surface.
5. **End-frame wiring** — node type built, unused; cheap to finish once T30 lands.
6. **Jobs drawer prompt visibility + pause/cancel/clear** — old app's most-cited "is it hung, what is it doing" surface; current drawer only shows kind/%/$.
7. **Alpha-aware in-app playback** — needed once overlay/animation renders are reviewable in-card.
8. **Chained frames / cross-beat continuity ("+3 more")** — smaller; old app's escape hatch for a bad batch.

## Dropped on purpose (per brain audit's own verdicts, confirmed absent in v3)

- Plan versions / story lock — superseded by cuts/variants model (not yet built, but deliberately not a port target).
- mtime-keyed render approval — replaced by content-hash approval (`graph/approvals.py`), a strict improvement.
- `~/cc/animator/<client>` / `~/studio/assets/<client>` brand storage outside the project — replaced by versioned in-repo `packages/brandkit/kits/<client>/`.
- Story-units Ingest/Edit/Finish/Deliver read-only views, Enrich's Gio-backlog message — brain doc marks these DROP; none found in post3, consistent.
- Density slider / global re-plan — brain doc: planner proposes spans, never replaces; not present in v3, consistent with that decision.
- Live Resolve placement scripting (`place.py`) — v3 exports OTIO instead; Resolve import behavior is an open human spike (H1), not yet a code decision either way.
