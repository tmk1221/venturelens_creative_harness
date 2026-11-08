import { useEffect, useRef, useState } from 'react'
import type { Source } from '../../api/types'
import { useCutStore } from '../../store/cutStore'
import { hasCrossedBoundary, scheduleForFrame, totalFrames } from './schedule'
import { Waveform } from './Waveform'

interface Props {
  pid: string
  /** bumped by the parent (e.g. word click) to request a seek to `seekFrame`. */
  seekToken?: number
  seekFrame?: number
  onFrame?: (frame: number) => void
}

function audioUrl(pid: string, sourceId: string): string {
  return `/api/projects/${pid}/media/${sourceId}/audio`
}

function formatTimecode(seconds: number): string {
  const s = Math.max(0, seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${sec.toFixed(2).padStart(5, '0')}`
}

function sourceLabel(source: Source | undefined, sourceId: string): string {
  if (!source) return sourceId.slice(0, 6)
  return `${source.role} · ${sourceId.slice(0, 6)}`
}

// T22: Post is an audio-only editor -- picture judgement (angles, visual flubs, lip-sync)
// happens in Resolve, where the operators already work. This plays each segment's
// sync-group audio proxy (Cut/timeline still carries `angle_source_id` for export, but the
// monitor here follows `audio_source_id`), using the same pooled two-element preload and
// segment scheduler T19 built for video.
export function Monitor({ pid, seekToken, seekFrame, onFrame }: Props) {
  const timeline = useCutStore((s) => s.timeline)
  const cut = useCutStore((s) => s.cut)
  const sourcesById = useCutStore((s) => s.sourcesById)
  const fps = cut?.fps ? cut.fps.num / cut.fps.den : 24000 / 1001

  const audioRefs = [useRef<HTMLAudioElement>(null), useRef<HTMLAudioElement>(null)]
  const [activeSlot, setActiveSlot] = useState<0 | 1>(0)
  const [activeIndex, setActiveIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [frame, setFrame] = useState(0)
  const rafRef = useRef<number | null>(null)

  const total = totalFrames(timeline)

  // Load the active segment's audio proxy into the active slot on timeline/index change.
  useEffect(() => {
    const seg = timeline[activeIndex]
    const audio = audioRefs[activeSlot].current
    if (!seg || !audio) return
    const url = audioUrl(pid, seg.audio_source_id)
    if (!audio.src.endsWith(url)) audio.src = url
    audio.currentTime = seg.source_start
    if (playing) void audio.play().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, timeline, pid])

  // Sync the active element's play/pause state with `playing`. Without this, pressing the
  // Play button only flips React state -- nothing else here calls `.play()` except the
  // segment-load effect (which doesn't re-run on a bare play/pause toggle) and the
  // boundary-crossing swap, so playback would never actually start from a standing stop.
  useEffect(() => {
    const audio = audioRefs[activeSlot].current
    if (!audio) return
    if (playing) void audio.play().catch(() => {})
    else audio.pause()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, activeSlot])

  // Preload the next segment into the idle slot.
  useEffect(() => {
    const schedule = scheduleForFrame(timeline, timeline[activeIndex]?.start_frame ?? 0)
    const nextIndex = schedule?.nextIndex
    const idleSlot = activeSlot === 0 ? 1 : 0
    const audio = audioRefs[idleSlot].current
    if (nextIndex === null || nextIndex === undefined || !audio) return
    const nextSeg = timeline[nextIndex]
    if (!nextSeg) return
    const url = audioUrl(pid, nextSeg.audio_source_id)
    if (!audio.src.endsWith(url)) audio.src = url
    audio.currentTime = nextSeg.source_start
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex, activeSlot, timeline, pid])

  function seekToFrame(target: number) {
    const schedule = scheduleForFrame(timeline, target)
    if (!schedule) return
    const seg = timeline[schedule.activeIndex]
    const audio = audioRefs[activeSlot].current
    if (!seg || !audio) return
    audio.currentTime = seg.source_start + ((target - seg.start_frame) / Math.max(1, seg.duration_frames)) * (seg.source_end - seg.source_start)
    setActiveIndex(schedule.activeIndex)
    setFrame(target)
    // `frame` above is this component's own display state (the readout) -- without also
    // telling the parent, `EditWorkspace`'s `currentWordId` (and so the transcript's
    // highlighted/auto-scrolled word) only ever updates from the playing tick loop, so a
    // click-to-seek would move the monitor but leave the transcript highlight stuck on
    // whatever word was current before.
    onFrame?.(target)
  }

  // External seek request (e.g. click-a-word).
  useEffect(() => {
    if (seekFrame === undefined) return
    seekToFrame(seekFrame)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekToken])

  // Playback loop: read the active element's currentTime, convert to a cut frame, and swap
  // pooled elements when the frame crosses into the next segment. `<audio>` has no
  // requestVideoFrameCallback, so this always ticks on requestAnimationFrame.
  useEffect(() => {
    if (!playing) return
    let cancelled = false

    function tick() {
      if (cancelled) return
      const seg = timeline[activeIndex]
      const audio = audioRefs[activeSlot].current
      if (seg && audio) {
        const span = seg.source_end - seg.source_start
        const frac = span <= 0 ? 0 : (audio.currentTime - seg.source_start) / span
        const currentFrame = Math.round(seg.start_frame + frac * seg.duration_frames)
        setFrame(currentFrame)
        onFrame?.(currentFrame)

        if (hasCrossedBoundary(timeline, activeIndex, currentFrame)) {
          const nextIndex = activeIndex + 1
          if (nextIndex < timeline.length) {
            const idleSlot = activeSlot === 0 ? 1 : 0
            const idleAudio = audioRefs[idleSlot].current
            void idleAudio?.play().catch(() => {})
            audioRefs[activeSlot].current?.pause()
            setActiveSlot(idleSlot)
            setActiveIndex(nextIndex)
          } else {
            setPlaying(false)
          }
        }
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    tick()
    return () => {
      cancelled = true
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, activeIndex, activeSlot, timeline])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.code === 'Space' || e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPlaying((p) => !p)
      } else if (e.key.toLowerCase() === 'j') {
        setFrame((f) => Math.max(0, f - Math.round(fps)))
      } else if (e.key.toLowerCase() === 'l') {
        setFrame((f) => Math.min(total, f + Math.round(fps)))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [fps, total])

  const activeSeg = timeline[activeIndex] ?? null
  const currentSourceSeconds = activeSeg && activeSeg.duration_frames > 0
    ? activeSeg.source_start + ((frame - activeSeg.start_frame) / activeSeg.duration_frames) * (activeSeg.source_end - activeSeg.source_start)
    : 0

  return (
    <div className="flex flex-col gap-1 p-2 border-b border-neutral-200 dark:border-neutral-800">
      <div data-testid="monitor" className="relative">
        <audio ref={audioRefs[0]} data-testid="monitor-audio-0" data-active={activeSlot === 0} />
        <audio ref={audioRefs[1]} data-testid="monitor-audio-1" data-active={activeSlot === 1} />
        <div className="flex items-center justify-between text-neutral-500 font-mono text-xs px-1">
          <span data-testid="source-label">{sourceLabel(activeSeg ? sourcesById.get(activeSeg.audio_source_id) : undefined, activeSeg?.audio_source_id ?? '')}</span>
          <span data-testid="source-timecode">{formatTimecode(currentSourceSeconds)}</span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" data-testid="play-pause" onClick={() => setPlaying((p) => !p)} className="border border-neutral-300 dark:border-neutral-700 rounded px-2">
          {playing ? 'Pause' : 'Play'}
        </button>
        <span data-testid="frame-readout" className="text-neutral-500 font-mono">
          {frame} / {total}
        </span>
      </div>
      <Waveform
        pid={pid}
        sourceId={activeSeg?.audio_source_id ?? null}
        windowStart={activeSeg?.source_start ?? 0}
        windowEnd={activeSeg?.source_end ?? 1}
        playheadSeconds={currentSourceSeconds}
        onSeek={(seconds) => {
          if (!activeSeg) return
          const span = activeSeg.source_end - activeSeg.source_start
          const frac = span <= 0 ? 0 : (seconds - activeSeg.source_start) / span
          const target = Math.round(activeSeg.start_frame + frac * activeSeg.duration_frames)
          seekToFrame(target)
        }}
      />
    </div>
  )
}
