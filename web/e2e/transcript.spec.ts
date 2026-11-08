import { expect, test } from '@playwright/test'
import { mockApi, pid, cutId } from './mockApi'
import fixture from './fixtures/basic.json' with { type: 'json' }

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('select and delete a word range, then undo restores it', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()
  const before = await words.count()

  await words.nth(1).click()
  await page.keyboard.down('Shift')
  await words.nth(3).click()
  await page.keyboard.up('Shift')

  await page.getByTestId('action-delete').click()
  // `delete_words` round-trips through the mocked `/ops` route (an async `applyOp` call, not
  // awaited by the click handler itself) before `refetchCut` drops the deleted words out of
  // `visibleWords` -- a bare post-click snapshot of `words.count()` can win that race and see
  // the pre-delete count. Poll instead of asserting once immediately after the click.
  await expect(async () => {
    const afterDeleteVisible = await page.getByTestId('word').count()
    expect(afterDeleteVisible).toBeLessThan(before)
  }).toPass({ timeout: 5_000 })

  await page.keyboard.press('Meta+z')
  await expect(page.getByTestId('word')).toHaveCount(before)
})

test('show cuts reveals deleted words struck through, restore brings them back', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await words.nth(1).click()
  await page.keyboard.down('Shift')
  await words.nth(2).click()
  await page.keyboard.up('Shift')
  await page.getByTestId('action-delete').click()

  await page.getByTestId('show-cuts-toggle').check()
  await expect(page.locator('[data-testid="word"][data-deleted="true"]').first()).toBeVisible()
})

test('a stale revision op gets a 409 and the cut refetches', async ({ page }) => {
  const state = await mockApi(page)
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()

  state.forceConflictOnce = true
  await words.nth(1).click()
  await page.getByTestId('action-delete').click()
  await expect(page.getByTestId('conflict-banner')).toBeVisible()
})

test('restore brings a struck-through word back into the passage', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await words.nth(1).click()
  await page.getByTestId('action-delete').click()

  await page.getByTestId('show-cuts-toggle').check()
  const deleted = page.locator('[data-testid="word"][data-deleted="true"]').first()
  await expect(deleted).toBeVisible()
  await deleted.click()
  await expect(page.getByTestId('action-restore')).toBeVisible()
  await page.getByTestId('action-restore').click()
  await expect(page.locator('[data-testid="word"][data-deleted="true"]')).toHaveCount(0)
})

test('set angle opens the angle menu with the project source (behind the T22 settings flag)', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('post:showSetAngle', '1'))
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await words.first().click()
  await page.getByTestId('action-set-angle').click()
  await expect(page.getByTestId('angle-option').first()).toBeVisible()
})

test('click a word seeks the monitor and highlights it as current', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()
  await expect(page.getByTestId('frame-readout')).toHaveText('0 / 78')

  // "today" (index 2) starts at 0.6s in the fixture's 3.25s single-segment timeline (78
  // frames @ 24000/1001fps) -- clicking it should move the monitor there, not just select it.
  await words.nth(2).click()
  await expect(page.getByTestId('frame-readout')).not.toHaveText('0 / 78')
})

test('drag-to-move: dragging a selected word to a drop caret reorders the passage', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()

  const movingId = fixture.words.words[2]!.id // "today"
  const targetId = fixture.words.words[6]!.id // "talk"

  await page.locator(`[data-testid="word"][data-word-id="${movingId}"]`).click()
  // The transcript's move gesture is native HTML5 drag-and-drop (draggable + onDragStart/
  // onDragOver/onDrop); Playwright's pointer-based dragAndDrop doesn't reliably originate a
  // real browser drag session in headless Chromium, so dispatch the DragEvents directly --
  // this exercises the exact same React handlers a real drag would.
  // Dispatch dragstart+dragover, then let React flush the `dropBeforeWordId` state update
  // before dispatching drop -- a real drag fires dragover repeatedly as the mouse moves, so
  // this gap always exists for a real user; a single synchronous evaluate() would fire drop
  // against a stale pre-render closure.
  await page.evaluate(
    ({ movingId, targetId }) => {
      const source = document.querySelector(`[data-word-id="${movingId}"]`) as HTMLElement
      const target = document.querySelector(`[data-word-id="${targetId}"]`) as HTMLElement
      const dt = new DataTransfer()
      ;(window as unknown as { __dt: DataTransfer }).__dt = dt
      source.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer: dt }))
      target.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: dt }))
    },
    { movingId, targetId },
  )
  // Poll (rather than a fixed sleep) for React to flush `dropBeforeWordId` and render the
  // drop caret -- a fixed sleep was flaky under parallel worker load.
  await expect(page.getByTestId('drop-caret')).toBeVisible()
  await page.evaluate(
    (targetId) => {
      const target = document.querySelector(`[data-word-id="${targetId}"]`) as HTMLElement
      const dt = (window as unknown as { __dt: DataTransfer }).__dt
      target.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
    },
    targetId,
  )

  // `move_words` round-trips through the mocked `/ops` route the same way `delete_words`
  // does above -- `onMove`'s `applyOp` call is fire-and-forget from the drop handler, so a
  // bare post-drop snapshot of word order can win that race. Poll instead.
  await expect(async () => {
    const texts = await words.allTextContents()
    expect(texts.indexOf('today')).toBe(texts.indexOf('talk') - 1)
  }).toPass({ timeout: 5_000 })
})

test('swap take: picking a candidate replaces the selected range', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await words.first().click() // select "So"
  const before = await words.first().textContent()

  await page.getByTestId('action-swap-take').click()
  const candidate = page.getByTestId('swap-candidate').first()
  await expect(candidate).toBeVisible()
  await candidate.click()

  await expect(words.first()).not.toHaveText(before ?? '')
})

test('derive short from selection creates a derived cut and switches to it', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()
  await words.first().click()

  await page.getByTestId('action-derive').click()
  await page.getByTestId('derive-aspect-option').filter({ hasText: '9:16' }).click()

  await expect(page).toHaveURL(new RegExp(`/p/${pid}/edit/derived-cut-1$`))
})

test('jobs drawer toggle renders', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('jobs-drawer-toggle')).toBeVisible()
  await page.getByTestId('jobs-drawer-toggle').click()
  await expect(page.getByTestId('jobs-drawer')).toBeVisible()
})
