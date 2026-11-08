# Handoff — how to continue (any agent, including Codex)

State lives on disk, not in a chat. To resume: `cat AGENTS.md docs/TASKS.md`, `git log --oneline | head`,
then open the spec of the first unfinished task in `tasks/`.

Running with Codex: from this directory run `codex` and say:
"Read AGENTS.md and docs/HANDOFF.md, then do the next unfinished task in docs/TASKS.md."
Codex reads AGENTS.md automatically. One task per session keeps context small; start a fresh session per task.
If a task was left `in-progress`, run its tests first, read `git status`/`git diff`, and finish it rather than restarting.

Writing new tasks: copy the shape of an existing spec (Goal, Read first, Build, Acceptance, Out of scope).
Keep each task to something one session can finish and test without external services.

Human-only steps are listed at the bottom of TASKS.md; agents must not attempt them.

## Environment gotchas
- `packages/post_core/.venv` is Python 3.14. The PyPI `opentimelineio` 0.18.x sdist builds but is broken on macOS + 3.14 ("bad any cast"); install it from git main until a fixed release ships:
  `.venv/bin/pip install "git+https://github.com/AcademySoftwareFoundation/OpenTimelineIO.git@main"`. If that ever fails, recreate the venv on Python 3.12 where wheels exist.
- H1 is still open: nobody has imported a T09 `.otio` into Resolve. Make a sample with the export test fixture and try it on a scratch project.
- T37 (vertical shorts), open points for T18/H1:
  - Which aspects each model offers is a guess in `recipes/fixtures/higgsfield/aspect_ratios.json` (Kling 16:9/9:16/1:1,
    so a 4:5 beat generates 9:16 and `video.generate` centre-crops to 4:5). T18 item 1 replaces it with real output.
    The choice is made at instantiate time; swapping the model in the graph inspector does not re-pick it.
  - `asset.verify` now fails generated video whose fps differs from the cut's. If Kling delivers 24 fps against a
    23.976 project, T18 must decide: conform in `video.generate`, or relax the check.
  - Exports are now `exports/<cut>_<aspect>_vNNN.otio` + `.manifest.json` + `.README.txt`; the timeline carries
    `post3` metadata (aspect, resolution, A-roll aspect). H1 answers whether Resolve uses any of it.
- T18 items 1 + 4 (free part, 2026-10-13, higgsfield CLI 1.1.25; the skill was written against 0.1.40). Surprises:
  - `model get --json` is `{display_name, job_type, type, params: [{name,type,default,required,enum?}], rules: [{cel,message}]}`
    (params a list, no pricing). `generate cost --json` is `{"credits": N}`. `models.py` now normalises both;
    fixtures in `recipes/fixtures/higgsfield/models/` are verbatim CLI output; `observed.json` holds the rest.
  - `nano_banana_2` still resolves but answers as `job_type: "nano_banana_pro"`; `nano_banana_pro` is now a real id
    (the skill's naming trap is out of date). Its refs param is `image_references`, not `input_images`.
  - `seedream_4` no longer exists; replaced by `seedream_v4_5` (MODEL_OPTIONS, fixtures, e2e). It has `quality`
    (basic/high), NOT `resolution`, and no 4:5: `still_generate.py` passes `--resolution 2k`, which will fail on it (item 2).
  - Kling 3.0: aspects 16:9/9:16/1:1 only (no 4:5, so the T37 crop path stands); mode std/pro/4k (default std);
    `sound` is a string on/off (default on); `start_image`/`end_image` objects, no `medias`; max duration 15 s
    (from the cost validator). `video_generate.py` sends the end image as a second `--start-image`, and has a
    boolean `--sound` it never forwards: fix both in item 2 (likely `--end-image`, `--sound on|off`).
  - Costs (credits): nano_banana_2 2 per still at 1k/2k, 4 at 4k; seedream_v4_5 1; Kling 5 s pro 10 with sound /
    7.5 without, std 8.75 / 6.25, 4k 30. The skill's 12.5 / 8.75 is stale. Cost does not vary with aspect.
  - fps is not in the contract. ffprobe of one earlier completed Kling pro 16:9 job (from `generate list`, read only)
    is 24/1 at 1928x1076, so item 5 must handle 24 vs a 23.976/29.97 project. `models.observed_fps()` exposes it.
  - `generate list --json` shows the server stores jobs as `params.medias[{role:"start_image", data:{id,url}}]` and
    `params.input_images`, i.e. the CLI renames params on the way in; result key is `result_url` (item 2 should confirm).
  - Item 4: lanes now live in `graph/lanes.py` (`default`: 2 added); `NodeRegistry.register` raises `UnknownLane`.
- T39 (media library, 2026-10-13): real projects live at `<library>/<Company>/<Project>/` (library =
  `POST3_LIBRARY`, else `library = …` in `~/.post3rc`, else `/Volumes/MediaDrive`), one folder per Resolve
  project, same name; house folders `Video/source Audio Transcript BRolls "AI Generations" Animations Renders
  Exports` + `.post3/`. `post project new --company C --project P --source … [--copy]`. A project is a library
  project when `Project.company` is set: exports go to `Exports/`, generated stills/video are also copied to
  `AI Generations/` (`library.publish_generated`, from `queue/artifacts.finalize_success`), kit lookup tries
  `<Company>/brand/` first (kit id = the company name). T34's "never under /Volumes" refusal is gone; the rule is
  now "never inside `Video/source` or a source's own folder". Tests point `POST3_LIBRARY`, `POST3_RC` and
  `POST3_HIGGSFIELD_BIN` at nothing (conftest), so no test reads the real library or runs the CLI.
  - Kits moved: `show` -> `/Volumes/MediaDrive/Sample Weekly Show/brand/`, `acme` -> `/Volumes/MediaDrive/Acme
    Automations/brand/` (Acme's company folder still holds the old Post app's project files, untouched). The repo
    keeps `kits/_template` and `kits/_demo` (Kestrel Demo Co., made up). `python -m brandkit init <client>` still
    writes into the repo's `kits/`: move the result to `<Company>/brand/` and do not commit it.
  - Show #37 is now `Sample Weekly Show/Show37 Your Agent Has a Computer/` with a Post3 project in it (source,
    audio proxy, peaks, the 70-word transcript, a first cut). The Resolve project should take the same name.
  - Model picker: every image/video model from `higgsfield model list` (fixture `recipes/fixtures/higgsfield/
    model_list.json`, verbatim), labelled with `display_name`, cached in `.post3/cache/higgsfield/model_list.json`,
    "Refresh list" in the graph inspector. Only `MODEL_OPTIONS` models have a price/capability chips; picking any
    other model is allowed but its cost estimate and params are unverified until someone tries it (real mode reads
    its contract with `higgsfield model get`).
  - Demo scripts still named for Acme (`scripts/import_acme_demo.py`, `make_acme_script_demo.py`, `make
    demo-acme`) read the old Post project on the drive; they are not tests and now load the `_demo` kit.
- Publishing the repo: the Acme and Show kits are still in git history (`packages/brandkit/kits/{acme,show}`),
  and so are client names in old specs/scripts. Before making the repo public, start from a fresh history or
  filter those paths out (`git filter-repo --path packages/brandkit/kits/acme --path packages/brandkit/kits/show
  --invert-paths`), and review `scripts/*acme*` and `tasks/`.

- T41 (2026-10-13): proposal badges are laid out in `web/src/suggest/passageLayout.ts` (lanes, per-line boxes,
  collision-free badges); only badges take the pointer now, so words under a proposal stay selectable. The
  header lost its kit-status chip and REAL badge (`useProvidersMode` still feeds the spend confirm). The Ingest
  page's Brand panel shows `GET /api/projects/{pid}/brand/index.html`, rendered IN MEMORY by
  `post_core.brand_page` from the kit's `design-system/` (re-rendered when its mtime/size signature moves) --
  nothing is written into the kit, so `brandkit render-design-system` output on disk is ignored. Saved
  (accepted) cards still carry no number; only proposals are numbered.

- T42 (2026-10-13): `Project.picture_mode` (`presenter` default | `audio_only`), set on the Ingest page, by
  `PATCH /api/projects/{pid}` or `post project set --picture-mode`. The suggest prompt has NO editorial rules
  any more (Travis: removed); the rationale is a plain "why this picture fits these words". In `audio_only`
  the prompt asks for full coverage and offers no aroll/behind, and `edit/suggest_coverage.py` enforces it
  after the reply: aroll and overlay-only proposals dropped, behind overlays stripped, overlaps trimmed (a
  beat inside another becomes its variant), gaps given word by word to the nearer beat, an empty stretch gets
  a plain filler beat; placed picture spans are tiled around, never touched. A Suggest run now REPLACES the
  pending proposals wholly inside its scope. Two ideas on the same words + layer become one proposal with
  `variants` / `active_variant` (`POST .../suggested-visuals/{id}/variant {index}`; "Variant A/B" on the
  card). Saved and proposed beats share one numbering (`numberBeats`), so an accepted card keeps its badge on
  the card and on its words. Show Demo and Show37 are `audio_only`. `post_api.suggest_models` now holds the
  suggest response shapes (models.py was over 400 lines).
