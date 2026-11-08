import { expect, test } from '@playwright/test'
import { cutId, mockIngestApi, pid } from './ingestMockApi'
import { SAMPLES } from './transcribeMockApi'

/** T35 acceptance (mocked API): "Transcribe…" shows the estimate and spends nothing until
 * Confirm; Confirm makes ONE budget capped at the shown amount and queues the job naming it;
 * the job's progress shows on the Ingest page and in the Jobs drawer (named SSE events). */
test('transcribe: estimate, one-click budget, progress on the page and in the Jobs drawer', async ({ page }) => {
  const state = await mockIngestApi(page)
  await page.goto(`/p/${pid}/ingest`)
  await expect(page.getByTestId('ingest-summary')).toContainText('Ready')

  await page.getByTestId('transcribe').click()
  await expect(page.getByTestId('spend-confirm-title')).toHaveText('Transcribe episode-37.mp4?')
  await expect(page.getByTestId('spend-confirm-estimate')).toHaveText('43 min of audio (Deepgram) ≈ 0.28 usd')
  await page.getByTestId('spend-confirm-cancel').click()
  expect(state.t35.budgets).toEqual([])
  expect(state.t35.transcribeBody).toBeNull()

  await page.getByTestId('transcribe').click()
  await page.getByTestId('spend-confirm-ok').click()
  await expect(page.getByTestId('transcribe-progress')).toContainText('Uploading the audio to Deepgram 40%')
  expect(state.t35.budgets).toHaveLength(1)
  const budget = state.t35.budgets[0]!
  expect(budget).toMatchObject({ cap: 0.28, unit: 'usd' })
  expect(budget.id).toMatch(/^transcribe-sg-1-\d+$/)
  expect(state.t35.transcribeBody).toEqual({ sync_group_id: 'sg-1', provider: 'deepgram', budget: budget.id, by: 'web' })
  await expect(page.getByTestId('transcribe')).toBeDisabled()

  await page.getByTestId('jobs-drawer-toggle').click()
  const row = page.getByTestId('job-row')
  await expect(row).toContainText('Transcription')
  await expect(row.getByTestId('job-progress')).toContainText('40%')

  state.t35.phase = 2 // Deepgram answered: the rest of the job's events arrive on reconnect
  await expect(row.getByTestId('job-result')).toHaveText('Transcribed 10 words, 2 speakers.')
  await expect(row.getByTestId('job-cost')).toHaveText('0.28 usd')
  await expect(page.getByTestId('transcript-ready')).toContainText('10 words')
  await expect(page.getByTestId('open-editor')).toBeVisible()
})

/** T35 acceptance (mocked API): click a speaker label -> rename everywhere (stored on the
 * transcript), and "Play a sample" plays that speaker's longest turn from the audio proxy. */
test('speakers: rename everywhere and play a sample', async ({ page }) => {
  const state = await mockIngestApi(page, { lockedCut: true })
  state.imported = true
  state.cutMade = true
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word')).toHaveCount(10)

  const labels = page.getByTestId('speaker-label')
  await expect(labels).toHaveText(['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_00'])

  await labels.nth(1).click()
  const popover = page.getByTestId('speaker-popover')
  await expect(popover).toContainText(`“${SAMPLES.SPEAKER_01.text}”`)
  await popover.getByTestId('speaker-sample-play').click()
  const audio = popover.getByTestId('speaker-sample-audio')
  await expect(audio).toHaveAttribute('src', `/api/projects/${pid}/media/src-1/audio`)
  await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.currentTime)).toBeGreaterThanOrEqual(SAMPLES.SPEAKER_01.start)
  // It stops by itself at the end of the sample (the longest turn), not at the end of the file.
  await expect(popover.getByTestId('speaker-sample-play')).toHaveText('Play a sample', { timeout: 10_000 })
  const stoppedAt = await audio.evaluate((a: HTMLAudioElement) => a.currentTime)
  expect(stoppedAt).toBeGreaterThanOrEqual(SAMPLES.SPEAKER_01.end)
  expect(stoppedAt).toBeLessThan(SAMPLES.SPEAKER_01.end + 1)
  expect(state.t35.audioRequests).toBeGreaterThan(0)

  await labels.nth(0).click()
  await page.getByTestId('speaker-name-input').fill('a podcast host')
  await page.getByTestId('speaker-rename-save').click()
  await expect(labels).toHaveText(['a podcast host', 'SPEAKER_01', 'a podcast host'])
  expect(state.t35.renames).toEqual([{ SPEAKER_00: 'a podcast host' }])
  await expect(page.getByTestId('word').first()).toHaveText('so')  // names never change word text
})
