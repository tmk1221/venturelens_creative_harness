import { expect, test } from '@playwright/test'
import { cutId, mockIngestApi, pid, RECORDING } from './ingestMockApi'

/** T34 acceptance (mocked API): the New project form -> the Ingest page following the job's
 * steps live -> import a transcript -> "Open editor" lands in the first cut. */
test('new project from a recording, through ingest, to the editor', async ({ page }) => {
  const state = await mockIngestApi(page)
  await page.goto('/')
  await page.getByTestId('new-project-link').click()
  await expect(page).toHaveURL('/new')

  await page.getByTestId('np-where-folder').check()
  await page.getByTestId('np-name').fill('Show 37 Sample')
  await expect(page.getByTestId('np-root')).toHaveAttribute('placeholder', '~/Post/show-37-keith')
  await page.getByTestId('np-sources').fill(RECORDING)
  await page.getByTestId('np-kit').selectOption('show')
  await page.getByTestId('np-submit').click()

  await expect(page).toHaveURL(`/p/${pid}/ingest`)
  expect(state.created).toEqual({ name: 'Show 37 Sample', root: '~/Post/show-37-keith', sources: [RECORDING], transcripts: [], brand_kit: 'show', copy_sources: false })

  const steps = page.getByTestId('ingest-step')
  await expect(steps).toHaveCount(6)
  await expect(steps.nth(4)).toContainText('Audio for episode-37.mp4')
  for (let i = 0; i < 6; i++) await expect(steps.nth(i)).toHaveAttribute('data-status', 'done')
  await expect(page.getByTestId('ingest-summary')).toContainText('Ready')

  // Audio ready: transcription (paid, confirmed first -- transcribe.spec.ts) or a free import.
  await expect(page.getByTestId('transcribe')).toBeEnabled()
  await expect(page.getByTestId('open-editor')).toHaveCount(0)
  await page.getByTestId('import-transcript').click()
  await page.getByTestId('transcript-path').fill('/Users/me/Downloads/episode-37.words.json')
  await page.getByTestId('transcript-import-submit').click()
  await expect(page.getByTestId('transcript-ready')).toContainText('10 words')

  await page.getByTestId('open-editor').click()
  await expect(page).toHaveURL(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word')).toHaveCount(10)
  expect(state.cutMade).toBe(true)
})

test('a project folder inside a footage folder is refused in plain words', async ({ page }) => {
  await mockIngestApi(page)
  await page.goto('/new')
  await page.getByTestId('np-where-folder').check()
  await page.getByTestId('np-name').fill('Sample')
  await page.getByTestId('np-root').fill('/Volumes/MediaDrive/Show/Ep/Video/source/keith')
  await page.getByTestId('np-sources').fill(RECORDING)
  await page.getByTestId('np-submit').click()
  await expect(page.getByTestId('np-error')).toContainText('is inside the footage folder')
  await expect(page).toHaveURL('/new')
})

test('a failing step shows its own sentence and offers Try again', async ({ page }) => {
  await mockIngestApi(page, { fail: true })
  await page.goto(`/p/${pid}/ingest`)
  const audio = page.locator('[data-testid="ingest-step"][data-step="audio:0"]')
  await expect(audio).toHaveAttribute('data-status', 'failed')
  await expect(audio.getByTestId('ingest-step-error')).toContainText('ffmpeg could not read the file')
  await expect(page.locator('[data-testid="ingest-step"][data-step="peaks:0"]')).toHaveAttribute('data-status', 'pending')
  await expect(page.getByTestId('ingest-summary')).toContainText('Audio for episode-37.mp4')
  await expect(page.getByTestId('transcript-actions')).toHaveCount(0)
  const rerun = page.waitForRequest((r) => r.url().endsWith(`/api/projects/${pid}/ingest/run`) && r.method() === 'POST')
  await page.getByTestId('ingest-retry').click()
  await rerun
})
