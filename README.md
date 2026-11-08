# VentureLens Creative Harness

An AI video-editing system for turning recorded interviews into finished client videos. You edit
the video by editing its transcript; an AI agent suggests visuals for each passage; image and video
models generate them in the client's brand style; the cut exports to DaVinci Resolve for finishing.

The same operations sit behind a web editor, a `post` CLI (JSON output) and an HTTP API, so people
and coding agents drive one system. Agents (Claude Code or Codex) run headless as workers, and
nothing that costs money runs without a shown estimate and a human approval.

**Stack:** Python core (Pydantic, SQLite job queue, ffmpeg) · FastAPI · React 19 + TypeScript ·
Deepgram (transcription) · Higgsfield (image/video generation) · Claude Code / Codex CLI (judgment
steps) · OpenTimelineIO export to Resolve. Built with Claude Code.

**For agents:** an MCP server exposes the editing core as 13 tools, tested by running a headless
Claude agent through editing tasks. See [`packages/post_mcp/`](packages/post_mcp/) and the
write-up of what broke and what changed, [`evals/EVALS.md`](evals/EVALS.md).

- Plan and rationale: `docs/ARCHITECTURE.md` (short).
- Current priorities and task specs: `docs/TASKS.md` and `tasks/*.md`.
- How to resume work in a fresh session: `docs/HANDOFF.md`.

## Layout

- `packages/post_core/` -- headless core: data model, atomic JSON store, build graph,
  SQLite queue + executor, edit ops, OTIO export, the `post` CLI.
- `packages/post_api/` -- thin FastAPI layer over `post_core` (no business logic).
- `packages/post_mcp/` -- MCP server over `post_core` for LLM agents; evals in `evals/`.
- `packages/brandkit/` -- brand kit schema, compilers, lint; `kits/_template` and the neutral `kits/_demo`.
- `web/` -- Vite + React 19 + TypeScript + Tailwind + zustand transcript editor. See
  `web/README.md` for its own npm commands.

## Running the demo

The demo project is built entirely from `ffmpeg lavfi` (synthetic color+tone media) and a
generated word list imported as a transcript -- no real footage, no network, no paid
provider calls. It lives under `.demo/` (git-ignored), separate from any real project.

Prerequisites (once): `packages/post_core/.venv` and `packages/post_api/.venv` built per
`docs/HANDOFF.md`, and `npm ci` run in `web/`.

```
make demo    # builds the demo project (first run only), starts post_api + vite, opens a browser tab
```

or, without auto-opening a browser:

```
make dev
```

Both print the exact edit URL (`http://127.0.0.1:5173/p/<project>/edit/<cut>`) once both
servers are up. Ctrl-C stops both processes. `make demo-project` just (re)builds the demo
project on disk under `.demo/` without starting any server; delete `.demo/` and run it (or
`make dev`/`make demo`) again to rebuild from scratch.

What you can click around: the transcript pane (select, delete/restore, swap take,
drag-to-move, "Derive short from selection" with a 16:9/9:16 aspect choice), the audio
monitor (play/pause, click-a-word-to-seek, click-to-seek on the waveform), and the jobs
drawer. Post plays audio only (T22) -- no source video, no video proxies; picture/angle
judgement happens in Resolve, so "set angle" is hidden behind a settings flag, off by
default (`localStorage.setItem('post:showSetAngle', '1')`).

## Starting a real project

Real projects live in the media library (`POST3_LIBRARY`, or `library = <path>` in
`~/.post3rc`; default `/Volumes/MediaDrive`), organised Company -> Project. Each project
folder matches one DaVinci Resolve project of the same name:

```
<library>/<Company>/brand/                  the company's brand kit (design-system layout)
<library>/<Company>/<Project>/              Video/source  Audio  Transcript  BRolls
                                            AI Generations  Animations  Renders  Exports  .post3/
```

One idempotent command takes a recording to a project the editor can open (re-run it to
resume: finished steps are skipped). It prints one JSON line per step:

```
post project new --company "Sample Weekly Show" --project "Show37 Your Agent Has a Computer" \
  --source "<library>/Sample Weekly Show/Show37 Your Agent Has a Computer/Video/source/clip.mp4" \
  [--copy] [--kit <id>] [--transcript words.json]
```

Recordings outside the project are referenced read-only, or copied into `Video/source` with
`--copy`. Post never writes inside `Video/source` or a recording's own folder. The project's
kit defaults to its company's `brand/`; OTIO exports land in `Exports/`, generated stills and
clips are copied to `AI Generations/`. Without `--company`, `--root <folder>` makes a project
anywhere else (temp and demo roots, tests). In the web app the same steps run as a job:
Projects -> "New project from a recording" (pick a company or type a new one), then the
Ingest page follows them live and offers "Import transcript..." and "Open editor".

Client brand kits never go in this repo; it ships `packages/brandkit/kits/_template` and the
neutral `_demo` kit (a made-up company) that tests and demos use.

## Tests

- Backend: `pytest` inside each package's own venv (`packages/post_core/.venv`,
  `packages/post_api/.venv`).
- Frontend: `npm test` (vitest, pure logic), `npm run build` (strict TS + Vite build), then
  `npm run e2e` (Playwright against a mocked API -- see `web/e2e/`). Details in
  `web/README.md`.
