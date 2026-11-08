import { describe, expect, it } from 'vitest'
import type { Cut, Passage, Word } from '../api/types'
import { buildBlocks, flattenBlocks, type WordIndex } from './blocks'

function word(id: string, i: number): Word {
  return { id, schema_version: 1, text: `w${i}`, start: i, end: i + 0.5, speaker: '', confidence: 1 }
}

function wordIndex(count: number): WordIndex {
  const words = Array.from({ length: count }, (_, i) => word(`w${i}`, i))
  const indexOf = new Map(words.map((w, i) => [w.id, i]))
  return { words, indexOf }
}

function passage(id: string, syncGroupId: string, startIndex: number, endIndex: number, angle = 'src1'): Passage {
  return {
    id, schema_version: 1, sync_group_id: syncGroupId,
    start_word_id: `w${startIndex}`, end_word_id: `w${endIndex}`,
    trims: { head: 0, tail: 0 }, angle_source_id: angle,
  }
}

function cut(passages: Passage[]): Cut {
  return { id: 'c1', schema_version: 1, aspect: { num: 16, den: 9 }, passages, spans: [], sections: [], variant_label: '' }
}

describe('buildBlocks', () => {
  it('one passage covering the whole transcript -> one block, no gaps', () => {
    const idx = wordIndex(5)
    const c = cut([passage('p1', 'sg1', 0, 4)])
    const blocks = buildBlocks(c, new Map([['sg1', idx]]))
    expect(blocks).toEqual([{ kind: 'passage', passage: c.passages[0], syncGroupId: 'sg1', startIndex: 0, endIndex: 4 }])
  })

  it('a deleted middle range shows up as a gap block between two passages', () => {
    const idx = wordIndex(10)
    const c = cut([passage('p1', 'sg1', 0, 3), passage('p2', 'sg1', 7, 9)])
    const blocks = buildBlocks(c, new Map([['sg1', idx]]))
    expect(blocks).toHaveLength(3)
    expect(blocks[1]).toEqual({ kind: 'gap', syncGroupId: 'sg1', startIndex: 4, endIndex: 6, afterPassageId: 'p1' })
  })

  it('no gap is inserted across different sync groups', () => {
    const idxA = wordIndex(5)
    const idxB = wordIndex(5)
    const c = cut([passage('p1', 'sgA', 0, 2), passage('p2', 'sgB', 0, 2)])
    const blocks = buildBlocks(
      c,
      new Map([
        ['sgA', idxA],
        ['sgB', idxB],
      ]),
    )
    expect(blocks.every((b) => b.kind === 'passage')).toBe(true)
  })
})

describe('flattenBlocks', () => {
  it('flattens passage + gap blocks into per-word entries, marking gaps deleted', () => {
    const idx = wordIndex(6)
    const c = cut([passage('p1', 'sg1', 0, 1), passage('p2', 'sg1', 4, 5)])
    const blocks = buildBlocks(c, new Map([['sg1', idx]]))
    const flat = flattenBlocks(blocks, new Map([['sg1', idx]]))
    expect(flat.map((w) => [w.wordId, w.deleted])).toEqual([
      ['w0', false],
      ['w1', false],
      ['w2', true],
      ['w3', true],
      ['w4', false],
      ['w5', false],
    ])
  })
})
