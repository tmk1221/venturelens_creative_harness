import { describe, expect, it } from 'vitest'
import { assignLanes, badgeWidth, lineBoxes, placeBadges, type Box } from './passageLayout'

function hit(a: Box, b: Box) {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom
}

describe('T41 passage layout', () => {
  it('gives overlapping passages separate lanes and reuses a lane once it is free', () => {
    // The real overlap shape: pairs on identical words, one starting inside another.
    const lanes = assignLanes([
      { id: 'a', startIndex: 1, endIndex: 4 },
      { id: 'b', startIndex: 5, endIndex: 7 },
      { id: 'e', startIndex: 2, endIndex: 4 },
      { id: 'f', startIndex: 5, endIndex: 7 },
    ])
    expect(lanes.get('a')).not.toBe(lanes.get('e'))
    expect(lanes.get('b')).not.toBe(lanes.get('f'))
    expect(lanes.get('b')).toBe(0) // a and e have ended by word 5
  })

  it('merges word boxes into one box per line', () => {
    const lines = lineBoxes([
      { top: 10, bottom: 30, left: 0, right: 40 },
      { top: 11, bottom: 30, left: 45, right: 90 },
      { top: 40, bottom: 60, left: 0, right: 30 },
    ])
    expect(lines).toEqual([
      { top: 10, bottom: 30, left: 0, right: 90 },
      { top: 40, bottom: 60, left: 0, right: 30 },
    ])
  })

  it('puts eight badges that want the same spot side by side, in number order, none overlapping', () => {
    const anchors = [3, 1, 4, 8, 2, 7, 5, 6].map((n) => ({ id: `s${n}`, n, left: 100, top: 50 }))
    const boxes = placeBadges(anchors)
    const ordered = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => boxes.get(`s${n}`)!)
    for (let i = 0; i < ordered.length; i++) {
      for (let j = i + 1; j < ordered.length; j++) expect(hit(ordered[i]!, ordered[j]!)).toBe(false)
    }
    expect(ordered.every((b) => b.top === 40)).toBe(true) // same line, not stacked
    for (let i = 1; i < ordered.length; i++) expect(ordered[i]!.left).toBeGreaterThan(ordered[i - 1]!.left)
  })

  it('leaves badges that do not collide where they want to be, and sizes two digits wider', () => {
    const boxes = placeBadges([
      { id: 'a', n: 1, left: 100, top: 50 },
      { id: 'b', n: 12, left: 300, top: 50 },
    ])
    expect(boxes.get('a')!.left).toBe(90)
    expect(boxes.get('b')!.left).toBe(290)
    expect(boxes.get('b')!.right - boxes.get('b')!.left).toBe(badgeWidth(12))
  })
})
