import { expect, test } from '@playwright/test'
import { mockRawTranscriptApi, pid, cutId } from './rawTranscriptMockApi'

test.beforeEach(async ({ page }) => {
  await mockRawTranscriptApi(page)
})

/** T27 item 2: the passage toolbar (`data-testid="passage-toolbar"`, "Add visual") must
 * actually appear next to the selection, not be silently rendered off-screen. Covers both
 * ways of making a selection the spec calls out: a mouse drag and a double-click. */
test('dragging across words shows the passage toolbar near the selection, and Add visual works', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()

  await words.nth(1).hover()
  await page.mouse.down()
  await words.nth(3).hover()
  await page.mouse.up()

  const toolbar = page.getByTestId('passage-toolbar')
  await expect(toolbar).toBeVisible()
  const toolbarBox = await toolbar.boundingBox()
  const wordBox = await words.nth(3).boundingBox()
  expect(toolbarBox).not.toBeNull()
  expect(wordBox).not.toBeNull()
  // The toolbar floats close to the selection, not pinned to the bottom of the transcript --
  // this is the exact bug: T25's `position: static` slot sat far below the visible words.
  // (Playwright's boundingBox() returns {x, y, width, height}, not {top, left}.)
  expect(Math.abs(toolbarBox!.y - wordBox!.y)).toBeLessThan(200)

  await page.getByTestId('action-add-visual').click()
  await expect(page.getByTestId('visual-dialog')).toBeVisible()
  await page.getByTestId('visual-kind-video').check()
  // T30c: Save is disabled until a brief is written -- the dialog's whole point now.
  await page.getByTestId('visual-brief').fill('Show the product on the desk.')
  await page.getByTestId('visual-save').click()
  await expect(page.getByTestId('visual-dialog')).not.toBeVisible()
  await expect(page.getByTestId('visual-card')).toHaveCount(1)
})

test('double-clicking a word shows the passage toolbar', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()

  await words.nth(2).dblclick()
  await expect(page.getByTestId('passage-toolbar')).toBeVisible()
  await expect(page.getByTestId('action-add-visual')).toBeVisible()
})

test('Escape dismisses the passage toolbar', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await words.nth(1).dblclick()
  await expect(page.getByTestId('passage-toolbar')).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(page.getByTestId('passage-toolbar')).not.toBeVisible()
})

test('the passage toolbar does not appear while the mouse is still held down', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()
  const a = await words.nth(2).boundingBox()
  const b = await words.nth(6).boundingBox()
  await page.mouse.move(a!.x + 2, a!.y + a!.height / 2)
  await page.mouse.down()
  await page.mouse.move(b!.x + b!.width - 2, b!.y + b!.height / 2, { steps: 6 })
  await expect(page.getByTestId('passage-toolbar')).toHaveCount(0)
  await page.mouse.up()
  await expect(page.getByTestId('passage-toolbar')).toBeVisible()
})
