# web

Vite + React 19 + TypeScript (strict) + Tailwind 4 + zustand transcript editor for Post v3.
Talks to `post_api` (FastAPI) through a typed client generated from its OpenAPI schema.

## Commands

- `npm run dev` — dev server on Vite's default port, proxying `/api` to `post_api` (set
  `POST_API_PORT` if it's not on 8000).
- `npm run build` — `tsc -b` (strict typecheck) then `vite build`.
- `npm run test` — vitest (pure logic: selection snapping, block/gap reconstruction, segment
  scheduling, frame↔word mapping).
- `npm run test:watch` — vitest in watch mode.
- `npm run gen:api` — regenerate `src/api/openapi.json` + `src/api/schema.ts` from the live
  `post_api` app (requires `packages/post_api/.venv`). Run this after any post_api route or
  model change.
- `npm run e2e` — Playwright, against a mocked API (see `e2e/`). `npm run e2e:ui` for the UI
  runner.

## Layout

- `src/api/` — generated OpenAPI types (`schema.ts`, do not hand-edit) + `client.ts` (typed
  fetch) + `types.ts` (short aliases).
- `src/store/` — zustand stores: `projectStore` (project registry), `cutStore` (the open
  cut: revision, transcript word indexes, selection, edit ops, undo/redo), `jobsStore`
  (SSE-fed queue events for the jobs drawer).
- `src/edit/` — the transcript editor: pure logic (`blocks.ts`, `selection.ts`,
  `monitor/schedule.ts`, `monitor/frameWord.ts` — all vitest-covered) plus the React views
  (`EditWorkspace.tsx`, `transcript/`, `monitor/`).
- `src/shell/`, `src/routes/` — app chrome (left nav, jobs drawer) and top-level pages.

## Notes / known gaps

- The server owns all edit and timeline maths (`post_core.edit.ops`/`ranges`); the client
  never recomputes a Cut, it only renders what `/ops` and `/timeline` return.
- "Derive short from selection" (toolbar) is not wired yet — `POST /cuts/derive` exists and
  is exercised by post_api tests, but no UI button calls it.
- Playwright coverage in `e2e/` is a mocked-API smoke pass, not the full acceptance matrix
  in `tasks/T11.md` (20k-word scroll budget and the video-boundary-crossing assertion are
  not yet automated).
