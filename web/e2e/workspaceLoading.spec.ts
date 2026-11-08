import { expect, test, type Route } from '@playwright/test'
import { mockApi, pid, cutId } from './mockApi'

/** T30e (owner click-through, items b/c): `EditWorkspace`'s loading and unreachable-backend
 * states. Both are about what renders BEFORE or WITHOUT a successful load, easiest to drive
 * deterministically by delaying or aborting specific routes on top of the ordinary mocked
 * fixture (`mockApi.ts`) rather than the real backend. */

test('shows a neutral loading state until cut and sources have both loaded, never the wrong layout', async ({ page }) => {
  let releaseCut: (() => void) | null = null
  const gate = new Promise<void>((resolve) => {
    releaseCut = resolve
  })
  await mockApi(page)
  // Layered on top of `mockApi`'s own `/cuts/{cutId}` handler (registered after it, so
  // Playwright's most-recently-registered-route-wins semantics try this one first) -- delays
  // just that response so `cut` stays null past the point sources/shoots have already
  // resolved, the exact window that used to render the media-backed layout by default before
  // `noMedia` had a real answer.
  await page.route(`**/api/projects/${pid}/cuts/${cutId}`, async (route: Route) => {
    await gate
    return route.fallback()
  })

  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('workspace-loading')).toBeVisible()
  await expect(page.getByTestId('raw-transcript')).toHaveCount(0)
  await expect(page.getByTestId('transcript-scroll')).toHaveCount(0)

  releaseCut!()
  await expect(page.getByTestId('workspace-loading')).toHaveCount(0)
  await expect(page.getByTestId('word').first()).toBeVisible()
})

test("shows \"Post's backend isn't running\" when the API is unreachable, not an empty page", async ({ page }) => {
  await page.route('**/api/**', (route: Route) => route.abort('connectionrefused'))
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await expect(page.getByTestId('backend-unreachable')).toBeVisible()
  await expect(page.getByTestId('backend-unreachable')).toContainText("Post's backend isn't running")
  await expect(page.getByTestId('word')).toHaveCount(0)
})
