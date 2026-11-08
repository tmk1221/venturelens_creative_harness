import { expect, test } from '@playwright/test'
import { cutId, mockLongShowApi, pid, words } from './longShowMockApi'

const LOAD_BUDGET_MS = 2000
const LONG_TASK_BUDGET_MS = 100

/** T34 acceptance: a 45-minute two-speaker show (~7,000 words) opens in the editor in under
 * 2 s -- measured from navigation to every word on the page -- and wheel-scrolling through it
 * records no long task over 100 ms (the same PerformanceObserver signal as perf.spec.ts). */
test('45-minute two-speaker transcript opens in under 2 s and scrolls without jank', async ({ page }) => {
  await mockLongShowApi(page)

  const t0 = Date.now()
  await page.goto(`/p/${pid}/edit/${cutId}`)
  await page.waitForFunction((n) => document.querySelectorAll('[data-testid="word"]').length === n, words.length, {
    polling: 16,
    timeout: 10_000,
  })
  const wallMs = Date.now() - t0
  const sinceNavigationMs = Math.round(await page.evaluate(() => performance.now()))
  const lastWordEnd = words[words.length - 1]!.end
  const line = `45-min fixture: ${words.length} words, ${(lastWordEnd / 60).toFixed(1)} min, 2 speakers -- ` +
    `loaded in ${wallMs} ms (goto -> all words rendered; ${sinceNavigationMs} ms since navigation start in the page)`
  console.log(line)
  test.info().annotations.push({ type: 'load-time', description: line })
  expect(wallMs, line).toBeLessThan(LOAD_BUDGET_MS)
  expect(words.length).toBeGreaterThan(6500)
  await expect(page.getByTestId('word').first()).toBeVisible()

  await page.evaluate(() => {
    const w = window as unknown as { __longTasks: number[] }
    w.__longTasks = []
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) w.__longTasks.push(entry.duration)
    }).observe({ entryTypes: ['longtask'] })
  })
  const paper = page.locator('.transcript-paper')
  const box = await paper.boundingBox()
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  const before = await paper.evaluate((el) => el.scrollTop)
  for (let i = 0; i < 60; i++) {
    await page.mouse.wheel(0, 800)
    await page.waitForTimeout(16)
  }
  const after = await paper.evaluate((el) => el.scrollTop)
  expect(after, 'the transcript itself scrolled').toBeGreaterThan(before + 10_000)

  const longTasks = await page.evaluate(() => (window as unknown as { __longTasks: number[] }).__longTasks)
  const worst = longTasks.length ? Math.max(...longTasks) : 0
  console.log(`45-min fixture scroll: ${longTasks.length} long task(s), worst ${Math.round(worst)} ms`)
  expect(worst, `long tasks during scroll: ${JSON.stringify(longTasks)}`).toBeLessThanOrEqual(LONG_TASK_BUDGET_MS)
})
