import { expect, test } from '@playwright/test'
import { mockRawTranscriptApi, pid, cutId } from './rawTranscriptMockApi'
import { mockSuggestApi } from './suggestMockApi'
import { overlapProposals } from './suggestOverlapFixture'

let suggestState: Awaited<ReturnType<typeof mockSuggestApi>>

test.beforeEach(async ({ page }) => {
  const cutState = await mockRawTranscriptApi(page)
  suggestState = await mockSuggestApi(page, cutState)
})

test('suggest visuals shows dashed proposals with a hover card; accept and dismiss remove them', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()

  await page.getByTestId('suggest-visuals-button').click()
  const decorations = page.getByTestId('suggestion-decoration')
  await expect(decorations).toHaveCount(2)
  await expect(page.getByTestId('accept-all-visuals')).toHaveText('Accept all (2)')

  await decorations.first().getByTestId('suggestion-badge').hover()
  const card = page.getByTestId('suggestion-hover-card')
  await expect(card).toBeVisible()
  await expect(card).toContainText('Show the calendar.')
  await expect(card).toContainText('Names a concrete date.')

  // Screenshot for the report: dashed proposals + a hover card open.
  await page.screenshot({ path: '../docs/screens/t13b-suggest.png' })

  await page.getByTestId('suggestion-accept').click()
  await expect(decorations).toHaveCount(1)

  await decorations.first().getByTestId('suggestion-badge').hover()
  await page.getByTestId('suggestion-dismiss').click()
  await expect(decorations).toHaveCount(0)
})

test('accept all clears every pending proposal and reports the count', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()

  await page.getByTestId('suggest-visuals-button').click()
  await expect(page.getByTestId('suggestion-decoration')).toHaveCount(2)

  await page.getByTestId('accept-all-visuals').click()
  await expect(page.getByTestId('suggestion-decoration')).toHaveCount(0)
  await expect(page.getByTestId('accept-all-note')).toHaveText('Accepted 2')
})

test('Adjust dismisses the suggestion and opens the Add visual dialog on its words', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()

  await page.getByTestId('suggest-visuals-button').click()
  const decorations = page.getByTestId('suggestion-decoration')
  await decorations.first().getByTestId('suggestion-badge').hover()
  await page.getByTestId('suggestion-adjust').click()

  await expect(page.getByTestId('visual-dialog')).toBeVisible()
  await expect(decorations).toHaveCount(1) // the adjusted one is gone, the other still pending
})

test('T40: proposals appear as numbered cards in the rail; an edited brief carries into the accepted card', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()
  const rail = page.getByTestId('visuals-rail')
  await rail.getByTestId('suggest-visuals-button').click()

  const cards = rail.getByTestId('proposed-card')
  await expect(cards).toHaveCount(2)
  await expect(cards.nth(0)).toContainText('Proposed')
  await expect(cards.nth(0)).toContainText('Live action')
  await expect(cards.nth(0)).toContainText('“today we are”')
  await expect(cards.nth(1)).toContainText('Motion graphic')
  await expect(cards.nth(0).getByTestId('proposed-card-badge')).toHaveText('1')
  await expect(page.locator('[data-suggestion-id="sugg-1"] [data-testid="suggestion-badge"]')).toHaveText('1')
  await expect(page.locator('[data-suggestion-id="sugg-2"] [data-testid="suggestion-badge"]')).toHaveText('2')

  const brief = cards.nth(0).getByTestId('proposed-brief')
  await brief.fill('A hand circles Friday on a paper calendar.')
  await cards.nth(0).getByTestId('proposed-accept').click()

  await expect(cards).toHaveCount(1)
  const saved = rail.getByTestId('visual-card')
  await expect(saved).toHaveCount(1)
  await expect(saved.getByTestId('visual-card-brief')).toHaveText('A hand circles Friday on a paper calendar.')
  await page.screenshot({ path: '../docs/screens/t40-proposed-cards.png' })
})

test('T40: clicking a passage focuses its card, and a card lights up its passage', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()
  await page.getByTestId('suggest-visuals-button').click()
  const cards = page.getByTestId('proposed-card')
  await expect(cards).toHaveCount(2)

  await page.locator('[data-suggestion-id="sugg-2"] [data-testid="suggestion-badge"]').click()
  await expect(page.locator('[data-suggestion-card-id="sugg-2"]')).toHaveClass(/is-focused/)
  await expect(page.locator('[data-suggestion-card-id="sugg-1"]')).toHaveClass(/is-dimmed/)

  await page.locator('[data-suggestion-card-id="sugg-1"] blockquote').click()
  await expect(page.locator('[data-suggestion-card-id="sugg-1"]')).toHaveClass(/is-focused/)
  await page.mouse.move(0, 0)
  await expect(page.locator('[data-testid="suggestion-decoration"][data-suggestion-id="sugg-1"]')).toHaveClass(/is-active/)
  await expect(page.locator('[data-testid="suggestion-decoration"][data-suggestion-id="sugg-2"]')).not.toHaveClass(/is-active/)
})

test('T40: while suggesting the button spins and the rail shows a placeholder; a failure shows in both places', async ({ page }) => {
  suggestState.suggestDelayMs = 800
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()
  const button = page.getByTestId('suggest-visuals-button')
  await button.click()
  await expect(button).toContainText('Suggesting visuals… (~20 s)')
  await expect(page.getByTestId('suggest-spinner')).toBeVisible()
  await expect(page.getByTestId('suggest-placeholder')).toBeVisible()
  await expect(page.getByTestId('proposed-card')).toHaveCount(2)
  await expect(page.getByTestId('suggest-placeholder')).toHaveCount(0)

  suggestState.suggestDelayMs = 0
  suggestState.failWith = 'claude CLI not found'
  await button.click()
  await expect(page.getByTestId('suggest-error')).toHaveText('claude CLI not found')
  await expect(page.getByTestId('suggest-rail-error')).toContainText('claude CLI not found')
  await expect(page.getByTestId('proposed-card')).toHaveCount(2)
})

test('T40: the suggest controls sit in the rail header, clear of the "Read the story" hint', async ({ page }) => {
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()
  await page.getByTestId('suggest-visuals-button').click()
  await expect(page.getByTestId('accept-all-visuals')).toBeVisible()
  await expect(page.getByTestId('visuals-rail').getByTestId('suggest-controls')).toBeVisible()
  const hint = await page.locator('.transcript-intro').boundingBox()
  for (const id of ['suggest-visuals-button', 'accept-all-visuals']) {
    const box = (await page.getByTestId(id).boundingBox())!
    const overlaps = hint && box.x < hint.x + hint.width && hint.x < box.x + box.width && box.y < hint.y + hint.height && hint.y < box.y + box.height
    expect(overlaps, `${id} overlaps the hint`).toBeFalsy()
  }
})

test('T41: eight overlapping proposals show eight distinct, non-overlapping badges', async ({ page }) => {
  await page.unrouteAll()
  const cutState = await mockRawTranscriptApi(page)
  await mockSuggestApi(page, cutState, structuredClone(overlapProposals))
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()
  await page.getByTestId('suggest-visuals-button').click()
  await expect(page.getByTestId('proposed-card')).toHaveCount(8)

  const badges = page.getByTestId('suggestion-badge')
  await expect(badges).toHaveCount(8)
  expect((await badges.allTextContents()).sort((a, b) => Number(a) - Number(b))).toEqual(['1', '2', '3', '4', '5', '6', '7', '8'])
  const boxes = []
  for (let i = 0; i < 8; i++) {
    await expect(badges.nth(i)).toBeVisible()
    boxes.push((await badges.nth(i).boundingBox())!)
  }
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i]!, b = boxes[j]!
      const hit = a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
      expect(hit, `badges ${i + 1} and ${j + 1} overlap`).toBeFalsy()
    }
  }

  // Passages on the same words sit in separate underline lanes; overlay is drawn differently.
  const lane = (id: string) => page.locator(`[data-testid="suggestion-decoration"][data-suggestion-id="${id}"]`)
  expect(await lane('ov-b').getAttribute('data-lane')).not.toBe(await lane('ov-f').getAttribute('data-lane'))
  expect(await lane('ov-a').getAttribute('data-lane')).not.toBe(await lane('ov-e').getAttribute('data-lane'))
  await expect(lane('ov-g')).toHaveClass(/is-overlay/)

  // Hovering one badge lights up that passage only.
  await lane('ov-f').getByTestId('suggestion-badge').hover()
  await expect(page.locator('.suggest-decoration.is-active')).toHaveCount(1)
  await expect(lane('ov-f')).toHaveClass(/is-active/)
  await page.screenshot({ path: '../docs/screens/t41-overlap-badges.png' })
})
