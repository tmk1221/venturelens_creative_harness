import type { TimelineSegment } from '../../api/types'

export interface ScheduleState {
  /** Index into `segments` of the segment currently (or about to be) playing. */
  activeIndex: number
  /** Index of the segment to preload into the idle `<video>` element, or null past the end. */
  nextIndex: number | null
}

/** Which timeline segment covers `frame`, and which one to preload next. Segments are
 * assumed ordered and contiguous (as `post_core.edit.ranges.timeline` guarantees). Pure and
 * cheap enough to call every scheduling tick -- no cumulative state. */
export function scheduleForFrame(segments: TimelineSegment[], frame: number): ScheduleState | null {
  if (segments.length === 0) return null
  let activeIndex = segments.findIndex(
    (s) => frame >= s.start_frame && frame < s.start_frame + Math.max(1, s.duration_frames),
  )
  if (activeIndex === -1) {
    // past the end (or before the start): clamp to the nearest real segment
    activeIndex = frame < segments[0]!.start_frame ? 0 : segments.length - 1
  }
  const nextIndex = activeIndex + 1 < segments.length ? activeIndex + 1 : null
  return { activeIndex, nextIndex }
}

/** True once `frame` has crossed into the segment after `fromIndex` -- the swap trigger for
 * the two pooled `<video>` elements. */
export function hasCrossedBoundary(segments: TimelineSegment[], fromIndex: number, frame: number): boolean {
  const current = segments[fromIndex]
  if (!current) return false
  return frame >= current.start_frame + current.duration_frames
}

/** Total duration in frames across every segment (the playhead's upper bound). */
export function totalFrames(segments: TimelineSegment[]): number {
  return segments.reduce((sum, s) => sum + s.duration_frames, 0)
}
