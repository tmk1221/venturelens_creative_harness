import { expect, test } from '@playwright/test'
import { mockLargeApi, pid, cutId } from './largeMockApi'

// T19 acceptance: "no long task > 100 ms while wheel-scrolling" a 20k-word transcript,
// asserted via PerformanceObserver (the same signal a real jank regression would trip).
test('20k-word transcript: wheel-scrolling stays under the long-task budget', async ({ page }) => {
  await mockLargeApi(page)
  await page.goto(`/p/${pid}/edit/${cutId}`)

  const words = page.getByTestId('word')
  await expect(words.first()).toBeVisible()
  // Let the (chunked) word fetch and first virtualized render settle before measuring --
  // the budget is about scroll jank, not initial load.
  await page.waitForTimeout(300)

  await page.evaluate(() => {
    const w = window as unknown as { __longTasks: number[] }
    w.__longTasks = []
    const obs = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) w.__longTasks.push(entry.duration)
    })
    obs.observe({ entryTypes: ['longtask'] })
  })

  const scrollEl = page.getByTestId('transcript-scroll')
  const box = await scrollEl.boundingBox()
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  for (let i = 0; i < 60; i++) {
    await page.mouse.wheel(0, 600)
    await page.waitForTimeout(16)
  }

  const longTasks = await page.evaluate(() => (window as unknown as { __longTasks: number[] }).__longTasks)
  const worst = longTasks.length ? Math.max(...longTasks) : 0
  expect(worst, `long tasks recorded during scroll: ${JSON.stringify(longTasks)}`).toBeLessThanOrEqual(100)
})
