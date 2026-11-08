import { describe, expect, it } from 'vitest'
import type { FlatWord } from './blocks'
import { extendSelection, orderedRange, passageIdsInRange, selectionSyncGroup, snapSelection } from './selection'

function flat(ids: string[], syncGroupId = 'sg1'): FlatWord[] {
  return ids.map((id, i) => ({
    wordId: id, text: id, syncGroupId, blockIndex: 0, deleted: false, passageId: `p${i}`,
    angleSourceId: null, isBlockStart: i === 0, start: i, end: i + 0.5,
  }))
}

describe('snapSelection', () => {
  it('returns the anchor/focus pair when both are present', () => {
    const f = flat(['a', 'b', 'c'])
    expect(snapSelection(f, 'a', 'c')).toEqual({ anchorWordId: 'a', focusWordId: 'c' })
  })

  it('returns null when either id is missing', () => {
    const f = flat(['a', 'b'])
    expect(snapSelection(f, 'a', 'zzz')).toBeNull()
  })
})

describe('orderedRange', () => {
  it('normalizes a forward selection', () => {
    const f = flat(['a', 'b', 'c', 'd'])
    expect(orderedRange(f, { anchorWordId: 'b', focusWordId: 'd' })).toEqual({ startWordId: 'b', endWordId: 'd' })
  })

  it('normalizes a backward selection (dragged right-to-left)', () => {
    const f = flat(['a', 'b', 'c', 'd'])
    expect(orderedRange(f, { anchorWordId: 'd', focusWordId: 'b' })).toEqual({ startWordId: 'b', endWordId: 'd' })
  })

  it('a single-word selection has equal start/end', () => {
    const f = flat(['a', 'b', 'c'])
    expect(orderedRange(f, { anchorWordId: 'b', focusWordId: 'b' })).toEqual({ startWordId: 'b', endWordId: 'b' })
  })
})

describe('extendSelection', () => {
  it('extends the focus forward, keeping the anchor fixed', () => {
    const f = flat(['a', 'b', 'c', 'd'])
    const sel = extendSelection(f, { anchorWordId: 'a', focusWordId: 'b' }, 1)
    expect(sel).toEqual({ anchorWordId: 'a', focusWordId: 'c' })
  })

  it('extends the focus backward past the anchor (selection can flip direction)', () => {
    const f = flat(['a', 'b', 'c', 'd'])
    let sel = { anchorWordId: 'c', focusWordId: 'c' }
    sel = extendSelection(f, sel, -1)
    sel = extendSelection(f, sel, -1)
    expect(sel).toEqual({ anchorWordId: 'c', focusWordId: 'a' })
  })

  it('clamps at the start of the list', () => {
    const f = flat(['a', 'b'])
    const sel = extendSelection(f, { anchorWordId: 'a', focusWordId: 'a' }, -1)
    expect(sel.focusWordId).toBe('a')
  })

  it('clamps at the end of the list', () => {
    const f = flat(['a', 'b'])
    const sel = extendSelection(f, { anchorWordId: 'b', focusWordId: 'b' }, 1)
    expect(sel.focusWordId).toBe('b')
  })
})

describe('passageIdsInRange', () => {
  it('returns distinct passage ids in order for a range spanning several passages', () => {
    const f: FlatWord[] = [
      { wordId: 'a', text: 'a', syncGroupId: 'sg1', blockIndex: 0, deleted: false, passageId: 'p1', angleSourceId: null, isBlockStart: true, start: 0, end: 0.5 },
      { wordId: 'b', text: 'b', syncGroupId: 'sg1', blockIndex: 0, deleted: false, passageId: 'p1', angleSourceId: null, isBlockStart: false, start: 0.5, end: 1 },
      { wordId: 'c', text: 'c', syncGroupId: 'sg1', blockIndex: 1, deleted: false, passageId: 'p2', angleSourceId: null, isBlockStart: true, start: 1, end: 1.5 },
    ]
    expect(passageIdsInRange(f, { startWordId: 'a', endWordId: 'c' })).toEqual(['p1', 'p2'])
  })

  it('skips gap words (no passage id) and returns [] when the range is missing', () => {
    const f: FlatWord[] = [
      { wordId: 'a', text: 'a', syncGroupId: 'sg1', blockIndex: 0, deleted: true, passageId: null, angleSourceId: null, isBlockStart: true, start: 0, end: 0.5 },
    ]
    expect(passageIdsInRange(f, { startWordId: 'a', endWordId: 'a' })).toEqual([])
    expect(passageIdsInRange(f, { startWordId: 'zzz', endWordId: 'zzz' })).toEqual([])
  })
})

describe('selectionSyncGroup', () => {
  it('returns the shared group when the whole range is one sync group', () => {
    const f = flat(['a', 'b', 'c'])
    expect(selectionSyncGroup(f, { startWordId: 'a', endWordId: 'c' })).toBe('sg1')
  })

  it('returns null when the range crosses sync groups', () => {
    const f = [...flat(['a', 'b'], 'sg1'), ...flat(['c', 'd'], 'sg2')]
    expect(selectionSyncGroup(f, { startWordId: 'b', endWordId: 'c' })).toBeNull()
  })
})
