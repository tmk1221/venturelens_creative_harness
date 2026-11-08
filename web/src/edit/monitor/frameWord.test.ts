import { describe, expect, it } from 'vitest'
import type { TimelineSegment } from '../../api/types'
import type { WordIndex } from '../blocks'
import { frameToWordId, wordIdToFrame } from './frameWord'

function seg(source_start: number, source_end: number, start_frame: number, duration_frames: number): TimelineSegment {
  return { passage_id: 'p1', sync_group_id: 'sg1', angle_source_id: 's1', audio_source_id: 's1', source_start, source_end, start_frame, duration_frames }
}

function wordIndex(): WordIndex {
  const words = [
    { id: 'w0', schema_version: 1, text: 'a', start: 0, end: 1, speaker: '', confidence: 1 },
    { id: 'w1', schema_version: 1, text: 'b', start: 1, end: 2, speaker: '', confidence: 1 },
    { id: 'w2', schema_version: 1, text: 'c', start: 2, end: 3, speaker: '', confidence: 1 },
  ]
  return { words, indexOf: new Map(words.map((w, i) => [w.id, i])) }
}

describe('frameToWordId', () => {
  it('maps a mid-segment frame to the word playing at that source time', () => {
    const segments = [seg(0, 3, 0, 30)]
    const idx = new Map([['sg1', wordIndex()]])
    // frame 15 of 30 -> halfway -> source time 1.5 -> word w1 (1..2)
    expect(frameToWordId(segments, 15, idx)).toBe('w1')
  })

  it('returns null when no segment covers the frame', () => {
    const segments = [seg(0, 3, 0, 30)]
    expect(frameToWordId(segments, 999, new Map([['sg1', wordIndex()]]))).toBeNull()
  })
})

describe('wordIdToFrame', () => {
  it('is the inverse of frameToWordId at a segment boundary', () => {
    const segments = [seg(0, 3, 0, 30)]
    const idx = new Map([['sg1', wordIndex()]])
    const frame = wordIdToFrame(segments, idx, 'sg1', 'w0')
    expect(frame).toBe(0)
  })

  it('returns null for a word not covered by any segment', () => {
    const segments = [seg(2, 3, 0, 10)]
    const idx = new Map([['sg1', wordIndex()]])
    expect(wordIdToFrame(segments, idx, 'sg1', 'w0')).toBeNull()
  })
})
