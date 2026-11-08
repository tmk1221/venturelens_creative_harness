/** T41: geometry for the numbered passages over the transcript, kept pure so it is testable
 * without a browser. Proposals often overlap (several start on the same word, or cover the
 * same words), so each one gets its own underline lane and its badge is nudged sideways until
 * it no longer covers another badge. */

export interface Box {
  top: number
  bottom: number
  left: number
  right: number
}

/** Badge size in px (`.suggest-passage-badge`): two-digit numbers are wider. */
export const BADGE_H = 18
export const BADGE_GAP = 3
export function badgeWidth(n: number): number {
  return n >= 10 ? 24 : 18
}

/** Greedy interval colouring over word positions: a passage takes the lowest lane no earlier
 * passage still occupies. Inputs need not be sorted; ties keep input order. */
export function assignLanes(items: { id: string; startIndex: number; endIndex: number }[]): Map<string, number> {
  const sorted = items.map((it, i) => ({ ...it, i })).sort((a, b) => a.startIndex - b.startIndex || a.i - b.i)
  const laneEnds: number[] = []
  const out = new Map<string, number>()
  for (const it of sorted) {
    let lane = laneEnds.findIndex((end) => end < it.startIndex)
    if (lane === -1) lane = laneEnds.length
    laneEnds[lane] = it.endIndex
    out.set(it.id, lane)
  }
  return out
}

/** Word boxes merged into one box per visual line (words whose tops agree within 3px). */
export function lineBoxes(words: Box[]): Box[] {
  const lines: Box[] = []
  for (const w of words) {
    const line = lines.find((l) => Math.abs(l.top - w.top) < 3)
    if (line) {
      line.left = Math.min(line.left, w.left)
      line.right = Math.max(line.right, w.right)
      line.bottom = Math.max(line.bottom, w.bottom)
    } else {
      lines.push({ ...w })
    }
  }
  return lines.sort((a, b) => a.top - b.top || a.left - b.left)
}

function overlaps(a: Box, b: Box): boolean {
  return a.left < b.right + BADGE_GAP && b.left < a.right + BADGE_GAP && a.top < b.bottom && b.top < a.bottom
}

/** One badge per passage, wanted just above-left of where it starts; any badge that would sit
 * on an earlier one moves right until it is clear, so badges for passages starting on the same
 * line sit side by side. Placed in `n` order, so the numbers read left to right. */
export function placeBadges(anchors: { id: string; n: number; left: number; top: number }[]): Map<string, Box> {
  const placed: Box[] = []
  const out = new Map<string, Box>()
  for (const a of [...anchors].sort((x, y) => x.n - y.n)) {
    const w = badgeWidth(a.n)
    const box: Box = { left: a.left - 10, top: a.top - 10, right: a.left - 10 + w, bottom: a.top - 10 + BADGE_H }
    for (let guard = 0; guard < 200 && placed.some((p) => overlaps(box, p)); guard++) {
      const blocker = placed.filter((p) => overlaps(box, p)).reduce((m, p) => Math.max(m, p.right), box.left)
      box.left = blocker + BADGE_GAP
      box.right = box.left + w
    }
    placed.push(box)
    out.set(a.id, box)
  }
  return out
}
