# Tasks (ordered). Status: todo | in-progress | done | blocked

| id | task | depends | status |
|----|------|---------|--------|
| T01 | brandkit: schema, Acme kit, compilers, lint | – | done |
| T02 | post_core: data model + atomic JSON store | – | done |
| T03 | post_core: worker contract + subprocess runner | – | done |
| T04 | post_core: build graph — node registry, input_hash, plan, staleness, approvals | T02 | done |
| T05 | post_core: SQLite queue + executor (lanes, authorisation, restart-safe, provider-limit hold) | T03 T04 | done |
| T06 | post CLI (JSON out) over core operations | T05 | done |
| T07 | ingest: transcript provider interface (Deepgram adapter + import), proxies + peaks via ffmpeg | T02 T03 | done |
| T08 | edit ops: passages from words (delete, restore, reorder, takes, angle), keep-ranges, undo snapshots | T02 | done |
| T09 | export: Cut → OpenTimelineIO (flattened angles, disabled alt-angle track, B-roll V2+, versioned names) | T08 | done |
| T10 | post_api: FastAPI over core + SSE events + OpenAPI → TS types | T06 | done |
| T11 | web: shell + transcript editor v1 (select, delete, reorder, proxy playback that skips cuts) | T10 T08 | done (gaps → T19) |
| T12 | recipes: live-action + motion-graphic graphs wrapping existing generators as workers (fakes in tests) | T05 T01 | done |
| T23 | post-picture-lock demo: script-as-transcript (`.demo-script`), no-media mode, collapsible sections, API lock fix | T22 | done |
| T24 | raw transcript, port post-transcript-first look, Add visual only; strip Rescript-style chrome | T23 | done |
| T25 | the ORIGINAL look, verbatim CSS/markup port, side-by-side screenshots | T24 | done |
| T26 | node-based generative editor in the Visuals rail: card view + @xyflow graph view, fake providers end to end (T13c+T14) | T24 T12 | done |
| T27 | fixes from first click-through: no cut dropdown, floating Add-visual toolbar, no stale UI on reload, Delete on card, full-screen graph, layout persistence | T26 | done |
| T28 | graph view: fluid (controlled nodes state, no re-layout on poll) and readable/aesthetic nodes with thumbnails | T27 | done |
| T29 | graph palette (all node types), model swap, typed inspector, plain-word card states | T28 | done |
| T30a | beat vocabulary + matrix + validators | T29 | done |
| T30b | backend recipes (overlay.place, end frame, +3 more, continuity, brief.write fake, aroll.regenerate stub + consent gate), suggester chooses everything, Decisions endpoint | T30a | done |
| T30c | dialog + card: overlay toggle/depth/position, flags, Generate prompt, Open in graph, two-gate animation, composite preview, alpha playback | T30b | done |
| T30d | graph nodes: in-node model picker, brief node, provided-clip picker, character node, overlay.place node, studio button | T30b | done |
| T30e | Decisions view, jobs drawer prompt+cancel, Playwright acceptance, screenshots | T30c T30d | done |
| T31 | spend safety: no implicit budgets, shown estimate = cap, real cost recorded, fake mode explicit + REAL badge | T30e | done |
| T32 | brandkit green after the Design System move: generate.py KeyError, pending style_block guard, tests | T20 | done |
| T33 | brand kit per project (no more fixed Acme) + `show` kit from example.com | T32 | done |
| T34 | new project from a local recording: `post project new`, Ingest page, root never on the footage drive | T22 T33 | done |
| T35 | transcription for a real 43-min episode: audio proxy, streamed, queued + authorised spend, .env in API, speaker names | T34 T31 | done |
| T36 | terminal-agent adapter: real Suggest visuals, brief.write, motion.from_frame (fakes in tests) | T33 | done |
| T37 | vertical shorts: B-roll at the cut's aspect, export names its format, render-contract checks | T33 | done |
| T39 | media library on the T7: Company → Project folders = Resolve projects; brand kits with the company, not in the repo; model picker | T37 | done |
| T40 | suggestions as editable proposed cards in the Visuals rail, numbered pairing with words, spinner, no overlap | T39 | done |
| T41 | all card numbers visible on overlapping passages, drop guessed/REAL header badges, live brand style guide in Ingest | T40 | done |
| T42 | picture mode (presenter / audio-only full B-roll) for the suggester, re-run replaces pending, variants, badges on accepted cards | T41 | done |
| T18 | real providers: Higgsfield still + video end to end, cost shapes, agent on a real slice, default lane (SUPERVISED, spends) | T31 T36 H8 | in-progress (items 1, 4 done) |
| T38 | Resolve read-back: editor's cut wins, markers → notes (port sync_edit), after H1 | T37 H1 | todo |
| T13a | editor look ported from post-transcript-first; takes (parked: pre-lock path) | T22 | parked |
| T13b | beats: suggest visuals, hover accept/adjust/dismiss, nothing pre-marked | T26 | done |
| T13c | enrich: beat cards from recipe graphs, cost, pick, approve (spec was T13) | T13b T12 | superseded (T26–T30; batch cost confirm → T31) |
| T14 | web: graph view (@xyflow/react) toggle | T13c | dropped (built in T26) |
| T15 | A-roll regen: provider interfaces (TTS, lipsync, twin), "regenerate line" as a take; fakes only | T08 T05 | parked (needs H2) |
| T16 | brandkit: house/brand/look layers, canonical template, status report, prompt templates | T01 | done |
| T17 | brandkit: split by medium (stills/video/animation), derive-style from images, series override | T16 | done |
| T19 | web editor: close T11 gaps (derive short, perf + playback e2e), `make demo`, README | T11 | done |
| T20 | brandkit: first-principles core, positive-only, generated UI shades, `init --from <website>` | T17 | done |
| T21 | real-footage demo: import Acme 2026-09-09 shoot read-only into `.demo-acme`, proxies, smoke test | T11 | done |
| T22 | audio-only editor: no video proxies, audio monitor, angles picked in Resolve | T19 T21 | done |

Specs: `tasks/T01.md` … Write the spec for a task before starting it if it does not exist
(plan sections to cite: data model §5, Resolve boundary §6, graphs §7, brand §8, A-roll §9).

Current focus (2026-10-13): first real video in Post3, a no-strings work sample for a podcast host (Sample Weekly Show
#37 "AI Is Becoming Permanent": a ~60 s short in his own voice + B-roll, 4:5 and 9:16, plus a re-cut of his 29 s
LinkedIn clip). T31–T37 are what that video needs; captions are out of scope for now (done outside Post3 if wanted).

## Human-only (Travis)
- H1 Resolve spike: import a T09 `.otio` into a scratch Resolve project; report what survives. Use the Sample short's
  first export (after T37) so the aspect/resolution metadata question is answered too.
- H5 Get the source media onto the SSD: Show #37 full episode (YouTube playlist) and Sample's 29 s LinkedIn clip.
  Private work-sample use only; nothing is published or tagged before Sample says yes.
- H6 Review the `show` brand kit's guessed fields (after T33; since T39 it lives at `/Volumes/MediaDrive/Sample Weekly Show/brand/`).
- H7 Run the real Deepgram transcription of #37 (~43 min, well under $1) and name the speakers (after T35). First check
  Deepgram's current nova-3 pre-recorded + diarization price: T35 estimates $0.0063/min (unverified; override with
  `deepgram_usd_per_minute` in `.post3/config.json`). Web: `POST3_REAL=1 make dev` -> Ingest -> "Transcribe…" -> Confirm.
  CLI: `post ingest transcribe --root <p> --sync-group <id> --estimate`, `post budget set --id t1 --cap <amount> --unit usd`,
  then the same with `--budget t1`. Name speakers by clicking a label in the editor, or `post transcript speakers`.
- H8 Set the Higgsfield credit budget for the supervised T18 session.
- H2 A-roll trial day: pick presenter, signed release, ElevenLabs PVC + HeyGen twin + sync.so test matrix (~$100–150).
- H3 Install compiled brand kit into the live skills (separate, after in-flight videos finish).
- H4 Old repo cleanup: all worktrees merged except post-transcript-first; diff `fix/start-frames-attention` vs main before deleting.
- Decided: no React Flow Pro purchase.
