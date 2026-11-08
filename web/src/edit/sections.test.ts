import { describe, expect, it } from 'vitest'
import type { Cut } from '../api/types'
import { isNoMediaCut } from './sections'

describe('isNoMediaCut', () => {
  it('true when every passage angle source is virtual', () => {
    const c: Cut = {
      id: 'c1', schema_version: 1, aspect: { num: 16, den: 9 }, sections: [], variant_label: '',
      passages: [
        { id: 'p1', schema_version: 1, sync_group_id: 'sg1', start_word_id: 'w0', end_word_id: 'w1', trims: { head: 0, tail: 0 }, angle_source_id: 'src1' },
      ],
      spans: [],
    }
    expect(isNoMediaCut(c, new Map([['src1', 'virtual']]))).toBe(true)
    expect(isNoMediaCut(c, new Map([['src1', 'real']]))).toBe(false)
  })

  it('false for an empty cut', () => {
    const c: Cut = { id: 'c1', schema_version: 1, aspect: { num: 16, den: 9 }, sections: [], variant_label: '', passages: [], spans: [] }
    expect(isNoMediaCut(c, new Map())).toBe(false)
  })
})
