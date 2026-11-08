import { useEffect, useRef } from 'react'

interface Props {
  pid: string
  sourceId: string | null
  /** seconds shown across the strip */
  windowStart: number
  windowEnd: number
  /** the currently playing point within [windowStart, windowEnd], for the playhead line */
  playheadSeconds: number | null
  peaksRate?: number
  /** click-to-seek: called with the source-relative second clicked */
  onSeek?: (seconds: number) => void
}

/** Canvas waveform for one source's peaks file (int8 min/max pairs at `peaksRate` Hz --
 * see `post_core.ingest.peaks`). Draws the slice covering [windowStart, windowEnd], the
 * current segment's cut boundaries at its edges (T22: every window shown here is one
 * passage -- a cut in and a cut out, not continuous footage), and supports click-to-seek. */
export function Waveform({ pid, sourceId, windowStart, windowEnd, playheadSeconds, peaksRate = 100, onSeek }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const peaksRef = useRef<Int8Array | null>(null)

  useEffect(() => {
    peaksRef.current = null
    if (!sourceId) return
    let cancelled = false
    fetch(`/api/projects/${pid}/media/${sourceId}/peaks`)
      .then((r) => (r.ok ? r.arrayBuffer() : null))
      .then((buf) => {
        if (!cancelled && buf) peaksRef.current = new Int8Array(buf)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [pid, sourceId])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const { width, height } = canvas
    ctx.clearRect(0, 0, width, height)
    ctx.fillStyle = 'rgba(120,120,130,0.15)'
    ctx.fillRect(0, 0, width, height)

    const peaks = peaksRef.current
    if (peaks && peaks.length >= 2) {
      const startIdx = Math.max(0, Math.floor(windowStart * peaksRate)) * 2
      const endIdx = Math.min(peaks.length, Math.ceil(windowEnd * peaksRate) * 2)
      const nPairs = Math.max(1, (endIdx - startIdx) / 2)
      const mid = height / 2
      ctx.fillStyle = '#60a5fa'
      for (let px = 0; px < width; px++) {
        const pairIdx = Math.floor((px / width) * nPairs)
        const i = startIdx + pairIdx * 2
        const lo = peaks[i] ?? 0
        const hi = peaks[i + 1] ?? 0
        const y1 = mid - (hi / 128) * mid
        const y2 = mid - (lo / 128) * mid
        ctx.fillRect(px, y1, 1, Math.max(1, y2 - y1))
      }
    }

    // Cut boundaries: this whole window is one passage, so both edges are cut points.
    ctx.fillStyle = '#ef4444'
    ctx.fillRect(0, 0, 2, height)
    ctx.fillRect(width - 2, 0, 2, height)

    if (playheadSeconds !== null && windowEnd > windowStart) {
      const x = ((playheadSeconds - windowStart) / (windowEnd - windowStart)) * width
      ctx.fillStyle = '#f59e0b'
      ctx.fillRect(Math.max(0, Math.min(width - 1, x)), 0, 1, height)
    }
  })

  function handleClick(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!onSeek) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const frac = (e.clientX - rect.left) / rect.width
    onSeek(windowStart + frac * (windowEnd - windowStart))
  }

  return (
    <canvas
      ref={canvasRef}
      data-testid="waveform"
      width={800}
      height={96}
      onClick={handleClick}
      className="w-full h-24 rounded bg-neutral-100 dark:bg-neutral-900 cursor-pointer"
    />
  )
}
