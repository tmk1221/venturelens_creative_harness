import { expect, test } from '@playwright/test'
import { mockBoundaryApi, pid, cutId, timeline } from './boundaryMockApi'

// T22 acceptance (rewritten from T19's video version): playback crossing a cut boundary
// swaps the pooled `<audio>` elements and lands within 20ms of the expected in-point. Plays
// two real one-second ffmpeg audio proxies (fixtures/audio/seg-{a,b}.m4a) so this exercises
// Monitor.tsx's actual swap tick, not a stand-in.
test('playback across a cut boundary swaps audio elements and lands within 20ms', async ({ page }) => {
  await mockBoundaryApi(page)
  await page.goto(`/p/${pid}/edit/${cutId}`)

  await expect(page.getByTestId('monitor')).toBeVisible()
  await expect(page.getByTestId('frame-readout')).toHaveText('0 / 50')

  await page.getByTestId('play-pause').click()

  // Poll frame-by-frame inside the page (rAF granularity) so the pause fires on the same
  // tick the app itself detects the boundary crossing -- doing this over the wire from
  // Playwright would add IPC latency larger than the 20ms tolerance.
  const result = await page.evaluate(() => {
    return new Promise<{ frame: number; currentTime: number; src: string } | null>((resolve) => {
      let ticks = 0
      function tick() {
        ticks += 1
        const readout = document.querySelector('[data-testid="frame-readout"]')
        const match = readout?.textContent?.match(/(\d+)\s*\//)
        const frame = match ? parseInt(match[1]!, 10) : 0
        if (frame >= 25) {
          ;(document.querySelector('[data-testid="play-pause"]') as HTMLButtonElement | null)?.click()
          const a0 = document.querySelector('[data-testid="monitor-audio-0"]') as HTMLAudioElement
          const a1 = document.querySelector('[data-testid="monitor-audio-1"]') as HTMLAudioElement
          const active = a0.dataset.active === 'true' ? a0 : a1
          resolve({ frame, currentTime: active.currentTime, src: active.currentSrc })
          return
        }
        if (ticks > 600) {
          resolve(null)
          return
        }
        requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    })
  })

  expect(result, 'never observed the boundary crossing').not.toBeNull()
  const { frame, currentTime, src } = result!

  // Segment B (index 1) is now active: its own proxy, source_start 0.
  const segB = timeline[1]!
  expect(src).toContain('src-b')
  const expectedTime = segB.source_start + ((frame - segB.start_frame) / segB.duration_frames) * (segB.source_end - segB.source_start)
  expect(Math.abs(currentTime - expectedTime)).toBeLessThanOrEqual(0.02)
})
