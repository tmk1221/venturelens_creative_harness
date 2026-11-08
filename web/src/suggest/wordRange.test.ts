import { describe, expect, it } from 'vitest'
import type { VisualSuggestion } from '../api/types'
import type { FlatWord } from '../edit/blocks'
import { kindLabel, numberBeats, railItems, suggestionsWithWords, variantLabel } from './wordRange'

function w(id: string, text: string): FlatWord {
  return { wordId: id, text, syncGroupId: 'sg1', blockIndex: 0, deleted: false, passageId: 'p1', angleSourceId: 'src1', isBlockStart: false, start: 0, end: 1 }
}

function suggestion(id: string, startWordId: string, endWordId: string, medium = 'live_action'): VisualSuggestion {
  return {
    id, transcript_id: 't1', start_word_id: startWordId, end_word_id: endWordId, medium,
    brief: 'brief', rationale: 'rationale', direction_note: '', flags: [], cast_refs: [], variants: [], active_variant: 0,
  }
}

describe('suggestionsWithWords', () => {
  const words = [w('a', 'one'), w('b', 'two'), w('c', 'three'), w('d', 'four')]

  it('resolves the covered word ids in order', () => {
    const result = suggestionsWithWords(words, [suggestion('s1', 'b', 'c')])
    expect(result).toHaveLength(1)
    expect(result[0]!.wordIds).toEqual(['b', 'c'])
  })

  it('drops a suggestion whose anchors no longer exist in the word list', () => {
    const result = suggestionsWithWords(words, [suggestion('s1', 'missing', 'c')])
    expect(result).toEqual([])
  })

  it('drops a suggestion whose end comes before its start', () => {
    const result = suggestionsWithWords(words, [suggestion('s1', 'c', 'a')])
    expect(result).toEqual([])
  })

  it('keeps multiple suggestions independently', () => {
    const result = suggestionsWithWords(words, [suggestion('s1', 'a', 'a'), suggestion('s2', 'c', 'd')])
    expect(result.map((r) => r.suggestion.id)).toEqual(['s1', 's2'])
    expect(result[1]!.wordIds).toEqual(['c', 'd'])
  })
})

describe('badge numbering and rail order (T40)', () => {
  const words = [w('a', 'one'), w('b', 'two'), w('c', 'three'), w('d', 'four')]

  it('numbers proposals 1..N in transcript order, whatever order the server sent', () => {
    const result = suggestionsWithWords(words, [suggestion('late', 'd', 'd'), suggestion('early', 'a', 'b')])
    expect(result.map((r) => [r.suggestion.id, r.n])).toEqual([['early', 1], ['late', 2]])
    expect(result[0]!.text).toBe('one two')
  })

  it('merges saved cards and proposals by their first word', () => {
    const proposed = suggestionsWithWords(words, [suggestion('s1', 'a', 'a'), suggestion('s2', 'd', 'd')])
    const saved = [{ id: 'card-c', wordIds: ['c'] }]
    const order = railItems(words, saved, proposed).map((r) => (r.kind === 'saved' ? r.card.id : r.item.suggestion.id))
    expect(order).toEqual(['s1', 'card-c', 's2'])
  })
})

describe('numberBeats (T42): saved and proposed beats share one numbering', () => {
  const words = [w('a', 'one'), w('b', 'two'), w('c', 'three'), w('d', 'four')]
  const card = (id: string, wordIds: string[]) => ({ span: { id }, wordIds })

  it('counts saved cards with proposals, in transcript order, saved first at the same start', () => {
    const proposed = suggestionsWithWords(words, [suggestion('s1', 'a', 'a'), suggestion('s2', 'd', 'd')])
    const { proposed: numbered, saved } = numberBeats(words, [card('sp', ['c'])], proposed)
    expect(numbered.map((p) => [p.suggestion.id, p.n])).toEqual([['s1', 1], ['s2', 3]])
    expect(saved.get('sp')).toBe(2)
  })

  it('an accepted proposal keeps its number, and so do the others', () => {
    const before = numberBeats(words, [], suggestionsWithWords(words, [suggestion('s1', 'a', 'b'), suggestion('s2', 'c', 'd')]))
    expect(before.proposed.map((p) => p.n)).toEqual([1, 2])
    const after = numberBeats(words, [card('sp1', ['a', 'b'])], suggestionsWithWords(words, [suggestion('s2', 'c', 'd')]))
    expect(after.saved.get('sp1')).toBe(1)
    expect(after.proposed[0]!.n).toBe(2)
  })

  it('a picture and an overlay on the same words share a number', () => {
    const { saved } = numberBeats(words, [card('pic', ['a', 'b']), card('ovl', ['a', 'b']), card('x', ['d'])], [])
    expect([saved.get('pic'), saved.get('ovl'), saved.get('x')]).toEqual([1, 1, 2])
  })

  it('labels variants A, B, C', () => {
    expect([0, 1, 2].map(variantLabel)).toEqual(['Variant A', 'Variant B', 'Variant C'])
  })
})

describe('kindLabel', () => {
  it('maps generative kinds to their display label', () => {
    expect(kindLabel('video')).toBe('Live action')
    expect(kindLabel('anim')).toBe('Motion graphic')
    expect(kindLabel('overlay')).toBe('Overlay')
  })

  it('falls back to the raw kind for anything else', () => {
    expect(kindLabel('mystery')).toBe('mystery')
  })
})
