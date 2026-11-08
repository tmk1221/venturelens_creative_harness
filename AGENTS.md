# Post v3 — instructions for any terminal agent (Claude, Codex)

Start here, every session: read `docs/HANDOFF.md`, then `docs/TASKS.md`. Do the first task whose
status is `todo` or `in-progress`, following its spec in `tasks/`. Update TASKS.md when you start and
finish. One commit per task. Do not start a task whose dependencies are not `done`.

- Plan and rationale: `docs/ARCHITECTURE.md` (short). Full plan and evidence live outside this repo in
  `~/cc/vl/brain/projects/post-app-master-plan-v3.md` and `post-v3-*.md`; read only the section a task cites.
- This is a NEW app beside the old one (`~/cc/post`, frozen, in production use). Never edit `~/cc/post`,
  `~/cc/post-*` worktrees, `~/.claude/skills`, `~/cc/animator`, `~/cc/vl`, or anything under `/Volumes`.
  Read them for reference only. The app itself writes to the media library (`/Volumes/MediaDrive/<Company>/
  <Project>/`, see `post_core/library.py`) when Travis runs it; agents still never write under `/Volumes`
  in development or tests unless a task explicitly authorises it. Tests use a temp `POST3_LIBRARY`.
- Client brand kits and project data never go in this repo (it will be public): kits live at
  `<library>/<Company>/brand/`; the repo keeps `kits/_template` and the neutral `kits/_demo` for tests/demos. Never start/stop the old backend, run paid generation, call Deepgram /
  Higgsfield / ElevenLabs / HeyGen, or touch DaVinci Resolve. Tests use temp dirs, fixtures and fakes.
- Python 3.12+ (`python3 -m venv .venv`; deps in `pyproject.toml`), stdlib first, few dependencies.
  Tests: `pytest`. Every task ends with tests passing and says so with the command output.
- Disk JSON under the project root is the source of truth; SQLite holds the queue and indexes only.
  Atomic writes (temp file + rename) under a file lock. A zero exit is not proof; artifacts are.
- Nothing spends money without an explicit authorisation recorded in the request. Enforce in the core.
- Keep files small and single-purpose (the old app died in one 1,700-line router). No file over ~400 lines.
- Report honestly: what was built, what was not, what is unverified.
- Secrets live in `.env` at the repo root (git-ignored, mode 600); `post_core` loads it at startup without overriding real environment variables. Never print, log, commit or echo key values; tests never need them.
