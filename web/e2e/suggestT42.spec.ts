import { expect, test } from '@playwright/test'
import { mockIngestApi, pid as ingestPid } from './ingestMockApi'
import { mockRawTranscriptApi, pid, cutId } from './rawTranscriptMockApi'
import { mockSuggestApi } from './suggestMockApi'

/** T42 (mocked API): the picture-mode setting on Ingest, switching a proposal's variant, and
 * accepted cards keeping their number on the card and on the words. */
const base = { transcript_id: 'tr-rt', overlay_depth: null, overlay_position: null, direction_note: '', flags: [], cast_refs: [], density_hint: null }
const ideaA = { medium: 'live_action', brief: 'Show the calendar.', rationale: 'The words name a date.' }
const ideaB = { medium: 'motion_graphic', brief: 'A countdown ticking to launch day.', rationale: 'Launch day is a deadline.' }
const pending = [
  { ...base, ...ideaA, id: 'sugg-1', start_word_id: 'w1', end_word_id: 'w3', variants: [ideaA, ideaB].map((i) => ({ ...base, ...i })), active_variant: 0 },
  { ...base, id: 'sugg-2', start_word_id: 'w8', end_word_id: 'w10', medium: 'motion_graphic', brief: 'Show the launch plan diagram.',
    rationale: 'Names the launch plan.', variants: [], active_variant: 0 },
]

test('picture mode is a setting on the Ingest page', async ({ page }) => {
  const state = await mockIngestApi(page)
  await page.goto(`/p/${ingestPid}/ingest`)
  const presenter = page.getByTestId('picture-mode-presenter')
  await expect(presenter).toBeChecked()
  await page.getByTestId('picture-mode-audio_only').click()
  await expect(page.getByTestId('picture-mode-audio_only')).toBeChecked()
  expect(state.pictureMode).toBe('audio_only')
})

test('a proposal with two ideas switches between Variant A and Variant B', async ({ page }) => {
  const cutState = await mockRawTranscriptApi(page)
  await mockSuggestApi(page, cutState, structuredClone(pending))
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()
  await page.getByTestId('suggest-visuals-button').click()

  const card = page.locator('[data-suggestion-card-id="sugg-1"]')
  const variants = card.getByTestId('proposed-variant')
  await expect(variants).toHaveText(['Variant A', 'Variant B'])
  await expect(page.locator('[data-suggestion-card-id="sugg-2"]').getByTestId('proposed-variant')).toHaveCount(0)
  await expect(card.getByTestId('proposed-brief')).toHaveValue('Show the calendar.')
  await variants.nth(1).click()
  await expect(variants.nth(1)).toHaveAttribute('aria-pressed', 'true')
  await expect(card.getByTestId('proposed-brief')).toHaveValue('A countdown ticking to launch day.')
  await expect(card.getByTestId('proposed-medium-chip')).toHaveText('Motion graphic')
  await page.screenshot({ path: '../docs/screens/t42-variants.png' })
})

test('an accepted card keeps its number on the card and on its words', async ({ page }) => {
  const cutState = await mockRawTranscriptApi(page)
  await mockSuggestApi(page, cutState, structuredClone(pending))
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()
  await page.getByTestId('suggest-visuals-button').click()
  await expect(page.locator('[data-suggestion-card-id="sugg-2"]').getByTestId('proposed-card-badge')).toHaveText('2')

  await page.locator('[data-suggestion-card-id="sugg-1"]').getByTestId('proposed-accept').click()
  const saved = page.getByTestId('visual-card')
  await expect(saved).toHaveCount(1)
  await expect(saved.getByTestId('saved-card-badge')).toHaveText('1')
  const wordBadge = page.getByTestId('saved-badge')
  await expect(wordBadge).toHaveText('1')
  await expect(page.locator('[data-suggestion-card-id="sugg-2"]').getByTestId('proposed-card-badge')).toHaveText('2')
  await expect(page.locator('[data-suggestion-id="sugg-2"] [data-testid="suggestion-badge"]')).toHaveText('2')

  await wordBadge.click()
  await expect(saved).toHaveClass(/is-focused/)
  await page.screenshot({ path: '../docs/screens/t42-accepted-badges.png' })
})
