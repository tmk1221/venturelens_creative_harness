# Architecture (decided 2026-09-21)

Python stays (Resolve API, OpenTimelineIO, existing scripts are Python). The internals are new:

1. **Content-addressed build graph is the only state system.** A Workflow is a graph of nodes. Each node
   has `input_hash = H(type, params, upstream output hashes, brand-kit hash)`. Done = an artifact dir on
   disk for that hash that passes the node's check. Stale = hash mismatch (old output stays visible).
   Approved = an approval record naming a content hash. The queue is "ready + authorised nodes", in SQLite,
   restart-safe. No separate evidence scanner, no in-memory chains.
2. **Headless core.** All operations are functions in `post_core`. `post` CLI (JSON out) and the HTTP API
   are thin clients. The web UI and coding agents use the same operations.
3. **Workers behind a contract.** A worker is a subprocess: explicit inputs + project root in, `##POST {json}`
   event lines out (`step,progress,prompt,cost,artifact,result`), result file, uniform exit codes
   (0 ok, 1 failed, 2 usage, 3 provider-limit/retry-later, 4 needs-human).

Layout: `packages/brandkit/` (standalone), `packages/post_core/` (model, store, graph, queue, workers, cli),
`packages/post_api/` (FastAPI, later), `web/` (Vite React TS, later).

Data model: Shoot → Source[] / SyncGroup[] / Transcript; Cut → Passage[] (word ranges, angle) + Span[]
(word-anchored, per layer) → Workflow → Asset; Deliverable; BrandKit. Timeline time is derived at export.
Editor: built here, not forked from Rescript (single-source model). Export: OpenTimelineIO, one-way, versioned.
Frontend later: React 19, TS, Tailwind 4, zustand, @xyflow/react; types generated from OpenAPI. Card view
default, graph view a toggle.

T22 (2026-09-21): Post plays audio only, not source video -- no video proxies, no encode step in the
editor. Picture judgement (angles, visual flubs, lip-sync) happens in Resolve, where the operators
already work; export still stacks every angle on its own track there.

T39 (2026-10-13): media and project data live in the media library on the T7 drive, Company -> Project.
`<library>/<Company>/<Project>/` is one DaVinci Resolve project (same name) with the house folders
`Video/source`, `Audio`, `Transcript`, `BRolls`, `AI Generations`, `Animations`, `Renders`, `Exports`, plus
Post3's `.post3/` store; the company's brand kit is `<library>/<Company>/brand/` (`post_core.library`).
Kit lookup: the company's `brand/`, then the repo's `kits/` (`_template`, the neutral `_demo`). The repo is
code plus the demo kit only, so it can be public; client kits and project data never go in it.
