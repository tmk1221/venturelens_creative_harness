import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// T26 acceptance flow, against a real post_api (POST3_FAKE_PROVIDERS=1) started by
// scripts/enrich_e2e_up.sh (see playwright.enrich.config.ts's webServer) -- not the
// route-mocked fixture the rest of web/e2e uses, because the node graph's plan/run/pick/
// approve/stale state machine lives server-side.
const __dirname = path.dirname(fileURLToPath(import.meta.url))
// T30d: `scripts/_enrich_e2e_seed.py` (via `enrich_e2e_up.sh`) now seeds one span per recipe
// kind up front -- `spanId` (video/live_action, the original T26 fixture field) plus
// `animSpanId`/`providedSpanId`/`overlaySpanId` -- so the graph-node acceptance tests below
// can open a motion_graphic/provided/overlay beat's graph directly instead of driving the
// dialog for each one.
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, '.enrich-fixture.json'), 'utf-8')) as {
  pid: string
  cutId: string
  spanId: string
  animSpanId: string
  providedSpanId: string
  overlaySpanId: string
}

/** Every T30d test below opens a span's card and toggles its graph the same way. T30e
 * (owner click-through): the graph panel is now rendered ONCE at the workspace level (see
 * `graphPanelStore`'s docstring), not nested inside the card's own DOM -- `enrich-graph-
 * toggle` still lives on the card, but `enrich-graph-panel` is looked up on `page`. */
async function openGraph(page: import('@playwright/test').Page, spanId: string) {
  await page.goto(`/p/${fixture.pid}/edit/${fixture.cutId}`)
  const card = page.locator(`[data-testid="visual-card"][data-span-id="${spanId}"]`)
  await expect(card).toBeVisible()
  const body = card.locator('[data-testid="enrich-card-body"]')
  await expect(body).toBeVisible({ timeout: 15_000 })
  await body.getByTestId('enrich-graph-toggle').click()
  const panel = page.getByTestId('enrich-graph-panel')
  await expect(panel).toBeVisible()
  return panel
}

/** T31: every spending click stops at the shell's confirm, which shows the estimate. */
async function confirmSpend(page: import('@playwright/test').Page, estimate: RegExp) {
  const dialog = page.getByTestId('spend-confirm')
  await expect(dialog).toBeVisible({ timeout: 10_000 })
  await expect(dialog.getByTestId('spend-confirm-estimate')).toHaveText(estimate)
  await dialog.getByTestId('spend-confirm-ok').click()
  await expect(dialog).toHaveCount(0)
}

test.setTimeout(60_000)

test('generate, pick, approve a still/video beat, then graph-view stale + rerun', async ({ page }) => {
  await page.goto(`/p/${fixture.pid}/edit/${fixture.cutId}`)

  const card = page.locator(`[data-testid="visual-card"][data-span-id="${fixture.spanId}"]`)
  await expect(card).toBeVisible()
  const body = card.locator('[data-testid="enrich-card-body"]')
  await expect(body).toBeVisible({ timeout: 15_000 })

  // Card view: brief is editable, Generate shows the estimate, confirming runs the stills.
  const brief = body.getByTestId('enrich-brief')
  await expect(brief).toBeVisible()

  await body.getByTestId('enrich-generate').click()
  await confirmSpend(page, /^3 stills ≈ \d+\.\d{2} credits$/)

  const variants = body.getByTestId('enrich-variant')
  await expect(variants).toHaveCount(3, { timeout: 20_000 })

  // T30e: the top-bar Decisions view -- this beat's `human.pick` node is genuinely
  // `NEEDS_PICK` right now, a real "pick" row from `GET .../decisions` (not a mock).
  const decisionsToggle = page.getByTestId('decisions-toggle')
  await expect(decisionsToggle).toBeEnabled({ timeout: 10_000 })
  await expect(page.getByTestId('decisions-count')).toBeVisible({ timeout: 10_000 })
  await decisionsToggle.click()
  const decisionsPanel = page.getByTestId('decisions-panel')
  await expect(decisionsPanel).toBeVisible()
  const pickRow = decisionsPanel.locator(`[data-testid="decision-row"][data-span-id="${fixture.spanId}"][data-kind="pick"]`)
  await expect(pickRow).toBeVisible()
  const screensDirDecisions = path.join(__dirname, '..', '..', 'docs', 'screens')
  fs.mkdirSync(screensDirDecisions, { recursive: true })
  await decisionsPanel.screenshot({ path: path.join(screensDirDecisions, 't30-decisions.png') })
  await pickRow.click()
  await expect(decisionsPanel).toHaveCount(0)

  const decisionGraphPanel = page.getByTestId('enrich-graph-panel')
  await expect(decisionGraphPanel).toBeVisible({ timeout: 10_000 })
  await expect(decisionGraphPanel.getByTestId('graph-inspector')).toContainText('Pick a frame', { timeout: 10_000 })
  await expect(card).toHaveClass(/is-focused/)
  // Close it again via the panel's own close button -- it's a `fixed inset-0` overlay, so it
  // visually covers the card's own toggle button underneath while open; the panel's own
  // "enrich-graph-close" (or Escape) is the only reliable way to dismiss it from here.
  await decisionGraphPanel.getByTestId('enrich-graph-close').click()
  await expect(decisionGraphPanel).toHaveCount(0)

  // Pick one -> confirm the video's estimate -> kicks off video.generate.
  await variants.first().getByTestId('enrich-pick').click()
  await confirmSpend(page, /\b1 video ≈ \d+\.\d{2} credits$/)
  await expect(body.getByTestId('enrich-clip')).toBeVisible({ timeout: 20_000 })

  // Approve binds the content hash (only enabled once asset.verify itself has finished).
  await expect(body.getByTestId('enrich-approve')).toBeVisible({ timeout: 15_000 })
  await body.getByTestId('enrich-approve').click()
  await expect(body.getByTestId('enrich-regen-note')).toBeVisible({ timeout: 10_000 })

  // Graph view: open it, see nodes/edges/states. T30e: the panel now renders at the
  // workspace level (`graphPanelStore`), not nested inside this card's own DOM.
  await body.getByTestId('enrich-graph-toggle').click()
  const panel = page.getByTestId('enrich-graph-panel')
  await expect(panel).toBeVisible()
  const graphNodes = panel.getByTestId('graph-node')
  await expect(graphNodes.first()).toBeVisible()
  const firstStill = panel.locator('[data-testid="graph-node"]', { hasText: `${fixture.spanId}-still0` })
  await expect(firstStill).toBeVisible()
  await expect(firstStill).toHaveAttribute('data-node-state', 'done')

  // T28 acceptance: screenshot of the demo beat's graph after Generate + Pick, thumbnails
  // visible on the still.generate nodes.
  const screensDir = path.join(__dirname, '..', '..', 'docs', 'screens')
  fs.mkdirSync(screensDir, { recursive: true })
  await expect(firstStill.locator('.graph-node-thumbs img, .graph-node-thumbs video').first()).toBeVisible({ timeout: 10_000 })
  await panel.screenshot({ path: path.join(screensDir, 't28-graph.png') })

  // T28 acceptance: a 40-step drag of a node reports no PerformanceObserver long task over
  // 50ms (dagre/relayout must not run mid-drag), and the node ends up where it was dropped.
  await page.evaluate(() => {
    const w = window as unknown as { __longTasks: number[] }
    w.__longTasks = []
    const obs = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) w.__longTasks.push(entry.duration)
    })
    obs.observe({ entryTypes: ['longtask'] })
  })
  const startBox = await firstStill.boundingBox()
  if (!startBox) throw new Error('drag node has no bounding box')
  const startX = startBox.x + startBox.width / 2
  const startY = startBox.y + startBox.height / 2
  const dx = 220
  const dy = 140
  const steps = 40
  await page.mouse.move(startX, startY)
  await page.mouse.down()
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(startX + (dx * i) / steps, startY + (dy * i) / steps)
    await page.waitForTimeout(16)
  }
  await page.mouse.up()

  const longTasks = await page.evaluate(() => (window as unknown as { __longTasks: number[] }).__longTasks)
  const worst = longTasks.length ? Math.max(...longTasks) : 0
  expect(worst, `long tasks recorded during a 40-step node drag: ${JSON.stringify(longTasks)}`).toBeLessThanOrEqual(50)

  const endBox = await firstStill.boundingBox()
  if (!endBox) throw new Error('drag node lost its bounding box')
  expect(Math.abs(endBox.x - startBox.x - dx)).toBeLessThan(12)
  expect(Math.abs(endBox.y - startBox.y - dy)).toBeLessThan(12)

  // ReactFlow's own pan/zoom pane sits on top of node content for dragging, so even a
  // forced Playwright click can land on the pane instead of the node's own onClick handler
  // -- dispatch the click via the DOM directly, same effect as a real click on the node.
  async function clickGraphNode(locator: ReturnType<typeof panel.locator>) {
    await locator.evaluate((el) => (el as HTMLElement).click())
  }

  // T29 item 1: a palette-added node lands unconnected; the user wires it by dragging
  // between named handles (`data-nodeid`/`data-handleid`, which @xyflow/react's own Handle
  // renders). New node ids are server-generated, so diff the sr-only id list before/after
  // each add to learn what got created.
  async function graphNodeIds(): Promise<string[]> {
    return panel.locator('.graph-node-id-sr').allTextContents()
  }
  async function addPaletteNode(testId: string): Promise<string> {
    const before = await graphNodeIds()
    await panel.getByTestId(testId).click()
    let added = ''
    await expect(async () => {
      const after = await graphNodeIds()
      const diff = after.filter((id) => !before.includes(id))
      expect(diff).toHaveLength(1)
      added = diff[0]!
    }).toPass({ timeout: 10_000 })
    return added
  }
  async function dragHandle(fromNodeId: string, fromHandle: string, toNodeId: string, toHandle: string) {
    const source = panel.locator(`[data-nodeid="${fromNodeId}"][data-handleid="${fromHandle}"]`)
    const target = panel.locator(`[data-nodeid="${toNodeId}"][data-handleid="${toHandle}"]`)
    await source.scrollIntoViewIfNeeded()
    await target.scrollIntoViewIfNeeded()
    const sBox = await source.boundingBox()
    const tBox = await target.boundingBox()
    if (!sBox || !tBox) throw new Error(`handle not found: ${fromNodeId}/${fromHandle} -> ${toNodeId}/${toHandle}`)
    await page.mouse.move(sBox.x + sBox.width / 2, sBox.y + sBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(tBox.x + tBox.width / 2, tBox.y + tBox.height / 2, { steps: 10 })
    await page.mouse.up()
  }

  // Add a reference-image node and drag-connect it into the first still's "continuity"
  // input (valid: image -> image) -- marks that still stale even though nothing re-ran yet.
  await firstStill.scrollIntoViewIfNeeded()
  await clickGraphNode(firstStill)
  const refNodeId = await addPaletteNode('graph-add-source-file')
  await dragHandle(refNodeId, 'file', `${fixture.spanId}-still0`, 'continuity')
  await expect(async () => {
    await expect(firstStill).toHaveAttribute('data-node-state', 'stale')
  }).toPass({ timeout: 10_000 })

  // Run from here -> confirm (the still plus what it leads to downstream) -> new stills.
  await clickGraphNode(firstStill)
  await panel.getByTestId('graph-run-from-here').click()
  await confirmSpend(page, /^1 still\b.* ≈ \d+\.\d{2} credits$/)
  await expect(async () => {
    await expect(firstStill).toHaveAttribute('data-node-state', /done|ready/)
  }).toPass({ timeout: 20_000 })

  // T29 item 1 (typed connections): a new Text-prompt node's output (type "prompt") is a
  // valid drag target for the recipe's own Video node's "motion_prompt" input (same type --
  // dropping onto that already-wired single-slot input replaces its old source, the Motion
  // prompt node, atomically) but a rejected one for its "start_image" input (type "image"):
  // `isValidConnection` never lets that second drag complete, so start_image stays wired to
  // its original source.
  const textPromptId = await addPaletteNode('graph-add-text-prompt')
  const videoNodeId = `${fixture.spanId}-video`
  const videoNode = panel.locator('[data-testid="graph-node"]', { hasText: videoNodeId })
  await videoNode.scrollIntoViewIfNeeded()
  await clickGraphNode(videoNode)
  const inspector = panel.getByTestId('graph-inspector')
  await expect(inspector).toContainText('motion_prompt: Motion prompt')
  await dragHandle(textPromptId, 'text', videoNodeId, 'motion_prompt')
  await expect(async () => {
    await clickGraphNode(videoNode)
    await expect(inspector).toContainText('motion_prompt: Text prompt')
  }).toPass({ timeout: 10_000 })
  await dragHandle(textPromptId, 'text', videoNodeId, 'start_image')
  await clickGraphNode(videoNode)
  await expect(inspector).toContainText('start_image: Pick a frame')

  // T29 item 2: swapping a still's model marks it stale (a fresh model id changes its
  // input_hash even though its params schema itself doesn't reshape).
  const secondStill = panel.locator('[data-testid="graph-node"]', { hasText: `${fixture.spanId}-still1` })
  await secondStill.scrollIntoViewIfNeeded()
  await clickGraphNode(secondStill)
  const modelSelect = panel.getByTestId('graph-model-select')
  await expect(modelSelect).toBeVisible()
  await modelSelect.selectOption('seedream_v4_5')
  await expect(async () => {
    await expect(secondStill).toHaveAttribute('data-node-state', 'stale')
  }).toPass({ timeout: 10_000 })

  // T29 item 3: typed inspector -- editing a param through its own field (not raw JSON) and
  // saving persists it server-side (Save disables once the draft matches the saved node).
  const promptField = panel.getByTestId('graph-field-prompt_text')
  await expect(promptField).toBeVisible()
  await promptField.fill('an updated custom brief for this still')
  await panel.getByTestId('graph-params-save').click()
  await expect(panel.getByTestId('graph-params-save')).toBeDisabled({ timeout: 10_000 })

  // T29 acceptance screenshot: the typed inspector open on a node.
  const screensDir29 = path.join(__dirname, '..', '..', 'docs', 'screens')
  fs.mkdirSync(screensDir29, { recursive: true })
  await panel.screenshot({ path: path.join(screensDir29, 't29-inspector.png') })

  // T29 item 1 (delete): deleting the earlier reference-image node removes its edge too --
  // the still node's "continuity" input goes back to unwired. (It's the reference-image
  // node, not the Text-prompt one, that's safe to delete here: Text-prompt is now the sole
  // source of the Video node's *required* motion_prompt input, and the server refuses to
  // save a workflow that would leave a required input unwired -- a pre-existing invariant,
  // `graph.workflow.validate`, this task doesn't change.)
  const refNode = panel.locator('[data-testid="graph-node"]', { hasText: refNodeId })
  await clickGraphNode(refNode)
  await panel.getByTestId('graph-delete-node').click()
  await expect(refNode).toHaveCount(0)
  await clickGraphNode(firstStill)
  await expect(inspector).toContainText('continuity: not wired')

  // T30d acceptance screenshot: the in-node model picker (price + capability chips) on a
  // still.generate node -- rendered unconditionally at the top of the node (spec: "a select
  // at the top of the node"), not only when selected.
  await clickGraphNode(firstStill)
  const compactPicker = firstStill.getByTestId('graph-node-model-select')
  await expect(compactPicker).toBeVisible()
  await expect(firstStill.getByTestId('graph-model-capabilities')).toContainText('start frame')
  const screensDirT30 = path.join(__dirname, '..', '..', 'docs', 'screens')
  fs.mkdirSync(screensDirT30, { recursive: true })
  await panel.screenshot({ path: path.join(screensDirT30, 't30-node-model.png') })
})

test('T30d: real Add-visual dialog creates a motion-graphic beat; its graph has brief Generate + studio button', async ({ page }) => {
  // Part 1: the real dialog, kind "Motion graphic", "Open in graph" -- this exit used to race
  // its own `ensureSpanWorkflow` call against the freshly-mounted card's own on-mount
  // instantiate call for the same brand-new span (both idempotent individually, but firing
  // both for a span with no `workflow_id` yet raced to write it back onto the cut): whichever
  // lost got a 409, silently swallowed, so the graph never opened. Fixed T30e two ways --
  // `RawTranscript.tsx::openInGraph` no longer calls `ensureSpanWorkflow` itself at all (the
  // card's own on-mount call is the only one now), and `useWorkflow`'s `start()` recovers
  // from a 409 by refetching the cut's `workflow_id` instead of erroring, so any *remaining*
  // concurrent instantiate (e.g. the workspace-level graph panel's own `useWorkflow` instance
  // opening at the same time) is safe too. This now exercises the real dialog -> `add_beat_
  // spans` -> card -> auto-opened graph path end to end.
  await page.goto(`/p/${fixture.pid}/edit/${fixture.cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()

  // Word indices 15-19 ("we also want to show") are left unclaimed by the seed script
  // specifically for this dialog-driven flow.
  await words.nth(15).hover()
  await page.mouse.down()
  await words.nth(19).hover()
  await page.mouse.up()
  await page.getByTestId('action-add-visual').click()
  const dialog = page.getByTestId('visual-dialog')
  await expect(dialog).toBeVisible()
  await dialog.getByTestId('visual-kind-anim').check()
  await dialog.getByTestId('visual-brief').fill('A quick animated chart of this quarter.')
  await dialog.getByTestId('visual-open-graph').click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByTestId('visual-card')).toHaveCount(5, { timeout: 10_000 })

  // The graph opens automatically, focused on the new beat's `brief.write` node.
  const openedPanel = page.getByTestId('enrich-graph-panel')
  await expect(openedPanel).toBeVisible({ timeout: 15_000 })
  await expect(openedPanel.getByTestId('graph-inspector')).toContainText('Brief', { timeout: 10_000 })
  await openedPanel.getByTestId('enrich-graph-close').click()
  await expect(openedPanel).toHaveCount(0)

  // Part 2: brief.write's Generate + the design node's studio button -- exercised on the
  // pre-seeded `animSpanId` beat (seeded server-side, so no dialog-exit race is involved)
  // via the same reliable `openGraph` helper the provided/overlay/character tests use.
  const panel = await openGraph(page, fixture.animSpanId)
  const briefNode = panel.locator('[data-testid="graph-node"]').filter({ has: page.getByTestId('node-brief') })
  await expect(briefNode).toBeVisible()
  const textarea = briefNode.getByTestId('graph-brief-instruction')
  await expect(textarea).toBeVisible()

  // Generate runs the brief.write node (fake mode). The button disables itself for the
  // click's own in-flight window (a local `busy` flag -- `state` alone can't signal that:
  // `brief.write` is already `ready`, which reads as "Generating…" too, before it has ever
  // run), then the node's own state reaches `done` once its fake-mode worker's manifest
  // lands on disk.
  const generateButton = briefNode.getByTestId('graph-brief-generate')
  await generateButton.click()
  await expect(async () => {
    await expect(briefNode).toHaveAttribute('data-node-state', 'done')
  }).toPass({ timeout: 15_000 })
  await expect(generateButton).toHaveText('Generate')

  // Studio button on the design node (`animation.design`) -- a fake in-page placeholder.
  const designNode = panel.locator('[data-testid="graph-node"]').filter({ has: page.getByTestId('node-studio') })
  await expect(designNode).toBeVisible()
  await designNode.getByTestId('graph-open-studio').click()
  await expect(page.getByTestId('graph-studio-placeholder')).toBeVisible()
})

test('T30d: provided.clip and overlay.place in-node pickers', async ({ page }) => {
  const providedPanel = await openGraph(page, fixture.providedSpanId)
  const providedNode = providedPanel.locator('[data-testid="graph-node"]').filter({ has: page.getByTestId('node-provided-clip') })
  await expect(providedNode).toBeVisible()
  const clipSelect = providedNode.getByTestId('graph-provided-select')
  // Seeded (T30d placeholder-path fix, `routes/enrich.py::span_workflow`) with the demo
  // catalogue's first fake clip rather than left unplannable.
  await expect(clipSelect).toHaveValue('provided/office-establishing.mp4')
  await clipSelect.selectOption('provided/team-standup.mp4')
  await expect(providedNode.getByTestId('graph-provided-out')).toHaveValue('9.5')
  await providedNode.getByTestId('graph-provided-in').fill('1')
  await expect(async () => {
    await expect(providedNode.getByTestId('graph-provided-in')).toHaveValue('1')
  }).toPass({ timeout: 10_000 })

  const overlayPanel = await openGraph(page, fixture.overlaySpanId)
  const overlayNode = overlayPanel.locator('[data-testid="graph-node"]').filter({ has: page.getByTestId('node-overlay-place') })
  await expect(overlayNode).toBeVisible()
  await expect(overlayNode.getByTestId('graph-overlay-depth')).toHaveValue('in_front')
  await expect(overlayNode.getByTestId('graph-overlay-position')).toHaveValue('lower-band')
  await overlayNode.getByTestId('graph-overlay-position').selectOption('right')
  await expect(async () => {
    await expect(overlayNode.getByTestId('graph-overlay-position')).toHaveValue('right')
  }).toPass({ timeout: 10_000 })
})

test('T30d: character node picked from the cast registry', async ({ page }) => {
  const panel = await openGraph(page, fixture.spanId)
  const before = await panel.locator('.graph-node-id-sr').allTextContents()
  await panel.getByTestId('graph-add-character').click()
  let charNodeId = ''
  await expect(async () => {
    const after = await panel.locator('.graph-node-id-sr').allTextContents()
    const diff = after.filter((id) => !before.includes(id))
    expect(diff).toHaveLength(1)
    charNodeId = diff[0]!
  }).toPass({ timeout: 10_000 })

  const charNode = panel.locator('[data-testid="graph-node"]', { hasText: charNodeId })
  await charNode.evaluate((el) => (el as HTMLElement).click())
  const picker = charNode.getByTestId('node-character-picker')
  await expect(picker).toBeVisible()

  // No cast entries exist yet -- the select is hidden, only "new character" is available.
  await expect(picker.getByTestId('graph-character-select')).toHaveCount(0)
  await picker.getByTestId('graph-character-new-name').fill('Dana')
  await picker.getByTestId('graph-character-new-add').click()

  // A successful create/pick clears the name input and the select now offers "Dana",
  // already chosen (this node's `source.file` path becomes `cast/Dana`, the registry having
  // no approved anchor yet).
  await expect(picker.getByTestId('graph-character-new-name')).toHaveValue('')
  await expect(picker.getByTestId('graph-character-select')).toBeVisible()
  await expect(picker.getByTestId('graph-character-select')).toHaveValue('Dana')
})
