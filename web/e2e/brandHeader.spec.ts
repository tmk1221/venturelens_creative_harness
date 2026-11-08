import { expect, test, type Page } from '@playwright/test'
import { mockIngestApi, pid as ingestPid } from './ingestMockApi'
import { cutId, mockRawTranscriptApi, pid } from './rawTranscriptMockApi'

/** T41 (mocked API): the shell header keeps the kit picker but shows no "guessed" kit badge
 * and no "REAL: spends credits" badge, even in real mode with a guessed kit; the Ingest page
 * shows the project's kit as a live style guide in a sandboxed iframe. */

async function mockShell(page: Page) {
  await page.route('**/api/doctor', (route) => route.fulfill({ json: { providers: 'real' } }))
  await page.route('**/api/brand-kits**', (route) =>
    route.fulfill({ json: { kits: [{ id: 'show', name: 'Sample Weekly Show', status: 'guessed', counts: { filled: 0, guessed: 23, pending: 12, total: 35 }, error: null }] } }),
  )
  await page.route((url) => url.pathname === `/api/projects/${pid}`, (route) =>
    route.fulfill({ json: { id: pid, name: 'Show Demo', root: '/tmp/show', schema_version: 1, brand_kit: 'show' } }),
  )
}

test('T41: the header shows the kit picker with no guessed or REAL badge', async ({ page }) => {
  await mockRawTranscriptApi(page)
  await mockShell(page)
  const doctor = page.waitForResponse('**/api/doctor')
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('word').first()).toBeVisible()
  await doctor
  await expect(page.getByTestId('brand-kit-select')).toHaveValue('show')
  await expect(page.getByTestId('real-badge')).toHaveCount(0)
  await expect(page.getByTestId('brand-kit-status')).toHaveCount(0)
  await expect(page.getByText('REAL: spends credits')).toHaveCount(0)
  await expect(page.getByTestId('brand-kit-picker')).not.toContainText('guessed')
})

test('T41: the Ingest page shows the kit as a live style guide and reloads when it changes', async ({ page }) => {
  await mockIngestApi(page)
  const kit = { signature: 'sig-1', colour: 'deep forest green' }
  const base = `/api/projects/${ingestPid}/brand`
  await page.route((url) => url.pathname.startsWith(base), (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === base) {
      return route.fulfill({ json: { kit_id: 'show', signature: kit.signature, page_url: `${base}/index.html`, approved_looks: ['approved-look-4x5.png'] } })
    }
    if (path === `${base}/index.html`) {
      return route.fulfill({ contentType: 'text/html', body: `<!doctype html><h1>Sample Weekly Show</h1><p class="colour">${kit.colour}</p><img alt="Approved look" src="assets/approved-look-4x5.png">` })
    }
    return route.fulfill({ status: 404, json: { detail: 'no such brand file' } })
  })

  await page.goto(`/p/${ingestPid}/ingest`)
  const panel = page.getByTestId('brand-panel')
  await expect(panel).toBeVisible()
  await expect(panel.getByTestId('brand-panel-kit')).toHaveText('show')
  const frameEl = panel.getByTestId('brand-panel-frame')
  await expect(frameEl).toHaveAttribute('sandbox', '')
  await expect(frameEl).toHaveAttribute('src', /index\.html\?v=sig-1/)
  const frame = page.frameLocator('[data-testid="brand-panel-frame"]')
  await expect(frame.locator('.colour')).toHaveText('deep forest green')

  kit.signature = 'sig-2'
  kit.colour = 'racing green'
  await panel.getByTestId('brand-panel-refresh').click()
  await expect(frameEl).toHaveAttribute('src', /index\.html\?v=sig-2/)
  await expect(frame.locator('.colour')).toHaveText('racing green')
})
