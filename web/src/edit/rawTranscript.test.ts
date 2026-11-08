import { describe, expect, it } from 'vitest'
import type { Span } from '../api/types'
import type { FlatWord } from './blocks'
import {
  coverage, layerFor, overlappingSpans, paragraphs, spanCards, swapPositionForDepthChange,
  validOverlayPositions, visualLabel,
} from './rawTranscript'

function w(id: string, text: string, start: number, end: number): FlatWord {
  return { wordId: id, text, syncGroupId: 'sg1', blockIndex: 0, deleted: false, passageId: 'p1', angleSourceId: 'src1', isBlockStart: false, start, end }
}

function span(id: string, layer: 'picture' | 'overlay', kind: string, startWordId: string, endWordId: string, extra: Partial<Span> = {}): Span {
  return {
    id, schema_version: 1, layer, kind, orphaned: false, provenance: 'human', note: '',
    flags: [], cast_refs: [], direction_note: '',
    start_anchor: { transcript_id: 't1', word_id: startWordId },
    end_anchor: { transcript_id: 't1', word_id: endWordId },
    ...extra,
  }
}

describe('paragraphs', () => {
  it('keeps words together under a short pause', () => {
    const words = [w('a', 'Hello', 0, 0.4), w('b', 'there', 0.5, 0.9)]
    expect(paragraphs(words)).toHaveLength(1)
  })

  it('breaks at a pause >= 1.5s', () => {
    const words = [w('a', 'Hello', 0, 0.4), w('b', 'there', 2.0, 2.4)]
    const groups = paragraphs(words)
    expect(groups).toHaveLength(2)
    expect(groups[0]!.words.map((x) => x.wordId)).toEqual(['a'])
    expect(groups[1]!.words.map((x) => x.wordId)).toEqual(['b'])
  })

  it('does not break at exactly under the threshold', () => {
    const words = [w('a', 'Hello', 0, 0.4), w('b', 'there', 1.7, 2.1)]
    expect(paragraphs(words)).toHaveLength(1)
  })

  it('T35: breaks where the speaker changes and marks each new turn for its name', () => {
    const s = (id: string, start: number, speaker: string) => ({ ...w(id, id, start, start + 0.3), speaker })
    const groups = paragraphs([s('a', 0, 'SPEAKER_00'), s('b', 0.4, 'SPEAKER_01'), s('c', 3, 'SPEAKER_01'), s('d', 3.4, 'SPEAKER_00')])
    expect(groups.map((g) => [g.words.map((x) => x.wordId).join(''), g.speaker, g.newTurn])).toEqual([
      ['a', 'SPEAKER_00', true], ['b', 'SPEAKER_01', true], ['c', 'SPEAKER_01', false], ['d', 'SPEAKER_00', true],
    ])
    expect(paragraphs([w('a', 'Hi', 0, 0.3)])[0]).toMatchObject({ speaker: '', newTurn: false })
  })
})

describe('spanCards', () => {
  const words = [w('a', 'one', 0, 0.4), w('b', 'two', 0.4, 0.8), w('c', 'three', 0.8, 1.2), w('d', 'four', 1.2, 1.6)]

  it('joins text/timing from the covered words, in transcript order', () => {
    const spans = [span('s2', 'picture', 'video', 'c', 'd'), span('s1', 'picture', 'aroll', 'a', 'a')]
    const cards = spanCards(words, spans)
    expect(cards.map((c) => c.span.id)).toEqual(['s1', 's2'])
    expect(cards[1]!.text).toBe('three four')
    expect(cards[1]!.start).toBe(0.8)
    expect(cards[1]!.end).toBe(1.6)
  })

  it('alternates beat tone for picture spans only, skipping overlays', () => {
    const spans = [span('s1', 'picture', 'aroll', 'a', 'a'), span('s2', 'overlay', 'overlay', 'a', 'a'), span('s3', 'picture', 'video', 'c', 'd')]
    const cards = spanCards(words, spans)
    const byId = Object.fromEntries(cards.map((c) => [c.span.id, c.beatTone]))
    expect(byId.s1).toBe(0)
    expect(byId.s2).toBeNull()
    expect(byId.s3).toBe(1)
  })

  it('drops orphaned spans and spans whose anchors are no longer in the word list', () => {
    const spans = [span('s1', 'picture', 'aroll', 'a', 'a', { orphaned: true }), span('s2', 'picture', 'aroll', 'zzz', 'zzz')]
    expect(spanCards(words, spans)).toEqual([])
  })
})

describe('coverage', () => {
  it('maps each covered word id to its cards', () => {
    const spans = [span('s1', 'picture', 'aroll', 'a', 'b')]
    const cards = spanCards(words(), spans)
    const cov = coverage(cards)
    expect(cov.get('a')!.map((c) => c.span.id)).toEqual(['s1'])
    expect(cov.get('b')!.map((c) => c.span.id)).toEqual(['s1'])
    expect(cov.has('c')).toBe(false)
  })
  function words(): FlatWord[] {
    return [w('a', 'one', 0, 0.4), w('b', 'two', 0.4, 0.8), w('c', 'three', 0.8, 1.2)]
  }
})

describe('overlappingSpans', () => {
  const words = [w('a', 'one', 0, 0.4), w('b', 'two', 0.4, 0.8), w('c', 'three', 0.8, 1.2), w('d', 'four', 1.2, 1.6)]

  it('finds same-layer spans overlapping the candidate range', () => {
    const spans = [span('s1', 'picture', 'aroll', 'b', 'c')]
    expect(overlappingSpans(words, spans, 'video', 'a', 'b').map((s) => s.id)).toEqual(['s1'])
    expect(overlappingSpans(words, spans, 'video', 'd', 'd')).toEqual([])
  })

  it('ignores spans on the other layer', () => {
    const spans = [span('s1', 'overlay', 'overlay', 'a', 'b')]
    expect(overlappingSpans(words, spans, 'video', 'a', 'b')).toEqual([])
    expect(overlappingSpans(words, spans, 'overlay', 'a', 'b').map((s) => s.id)).toEqual(['s1'])
  })
})

describe('layerFor / visualLabel', () => {
  it('maps kinds to their layer and label', () => {
    expect(layerFor('overlay')).toBe('overlay')
    expect(layerFor('video')).toBe('picture')
    expect(visualLabel('anim')).toBe('Motion graphic')
    expect(visualLabel('unknown-kind')).toBe('unknown-kind')
  })
})

// T30c: TS port of `post_core/model/cut.py`'s `valid_overlay_positions`/
// `swap_position_for_depth_change` -- the dialog's own inline matrix enforcement.
describe('validOverlayPositions', () => {
  it('behind is only ever legal over aroll', () => {
    expect(validOverlayPositions('aroll', 'behind')).toEqual(['right', 'left', 'full-frame'])
    expect(validOverlayPositions('video', 'behind')).toEqual([])
    expect(validOverlayPositions('anim', 'behind')).toEqual([])
  })

  it('in_front over aroll is a narrower set than over any other picture', () => {
    expect(validOverlayPositions('aroll', 'in_front')).toEqual(['right', 'left', 'lower-band'])
    expect(validOverlayPositions('video', 'in_front')).toEqual(['right', 'left', 'lower-band', 'center', 'full-width'])
    expect(validOverlayPositions('provided', 'in_front')).toEqual(['right', 'left', 'lower-band', 'center', 'full-width'])
  })
})

describe('swapPositionForDepthChange', () => {
  it('swaps lower-band <-> full-frame over aroll only', () => {
    expect(swapPositionForDepthChange('lower-band', 'aroll')).toBe('full-frame')
    expect(swapPositionForDepthChange('full-frame', 'aroll')).toBe('lower-band')
    expect(swapPositionForDepthChange('lower-band', 'video')).toBe('lower-band')
  })

  it('leaves non-participating positions untouched', () => {
    expect(swapPositionForDepthChange('right', 'aroll')).toBe('right')
    expect(swapPositionForDepthChange('center', 'video')).toBe('center')
  })
})
