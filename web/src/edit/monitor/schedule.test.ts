import { describe, expect, it } from 'vitest'
import type { TimelineSegment } from '../../api/types'
import { hasCrossedBoundary, scheduleForFrame, totalFrames } from './schedule'

function seg(passageId: string, start: number, duration: number, source = 's1'): TimelineSegment {
  return {
    passage_id: passageId, sync_group_id: 'sg1', angle_source_id: source, audio_source_id: source,
    source_start: 0, source_end: 1, start_frame: start, duration_frames: duration,
  }
}

describe('scheduleForFrame', () => {
  const segments = [seg('p1', 0, 10), seg('p2', 10, 5), seg('p3', 15, 20)]

  it('returns null for an empty timeline', () => {
    expect(scheduleForFrame([], 0)).toBeNull()
  })

  it('finds the active segment for a frame in the middle', () => {
    expect(scheduleForFrame(segments, 12)).toEqual({ activeIndex: 1, nextIndex: 2 })
  })

  it('finds the first segment at frame 0', () => {
    expect(scheduleForFrame(segments, 0)).toEqual({ activeIndex: 0, nextIndex: 1 })
  })

  it('nextIndex is null on the last segment', () => {
    expect(scheduleForFrame(segments, 16)).toEqual({ activeIndex: 2, nextIndex: null })
  })

  it('clamps to the last segment past the end', () => {
    expect(scheduleForFrame(segments, 999)).toEqual({ activeIndex: 2, nextIndex: null })
  })
})

describe('hasCrossedBoundary', () => {
  const segments = [seg('p1', 0, 10), seg('p2', 10, 5)]

  it('is false while still inside the segment', () => {
    expect(hasCrossedBoundary(segments, 0, 9)).toBe(false)
  })

  it('is true exactly at the boundary frame', () => {
    expect(hasCrossedBoundary(segments, 0, 10)).toBe(true)
  })
})

describe('totalFrames', () => {
  it('sums every segment duration', () => {
    expect(totalFrames([seg('p1', 0, 10), seg('p2', 10, 5)])).toBe(15)
  })
})
