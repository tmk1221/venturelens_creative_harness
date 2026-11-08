import type { FlatWord } from './blocks'

export interface Selection {
  /** Anchor is where the drag/shift-select started; focus is the live end. Order in the
   * flat word list may run either direction -- `orderedRange` normalizes it. */
  anchorWordId: string
  focusWordId: string
}

/** Selection is always word-granular (mouse and keyboard both operate on whole words), so
 * "snapping" is just: given any two word ids the user touched, find their positions in the
 * flat (display-order) word list and return the low/high pair, inclusive. Returns null if
 * either id isn't in the list (e.g. it scrolled out of a not-yet-loaded page). */
export function snapSelection(flat: FlatWord[], anchorWordId: string, focusWordId: string): Selection | null {
  const anchorIdx = flat.findIndex((w) => w.wordId === anchorWordId)
  const focusIdx = flat.findIndex((w) => w.wordId === focusWordId)
  if (anchorIdx === -1 || focusIdx === -1) return null
  return { anchorWordId, focusWordId }
}

/** The ordered [startWordId, endWordId] a selection covers in display order, or null if
 * either endpoint isn't in the flat list. */
export function orderedRange(flat: FlatWord[], selection: Selection): { startWordId: string; endWordId: string } | null {
  const anchorIdx = flat.findIndex((w) => w.wordId === selection.anchorWordId)
  const focusIdx = flat.findIndex((w) => w.wordId === selection.focusWordId)
  if (anchorIdx === -1 || focusIdx === -1) return null
  const [lo, hi] = anchorIdx <= focusIdx ? [anchorIdx, focusIdx] : [focusIdx, anchorIdx]
  return { startWordId: flat[lo]!.wordId, endWordId: flat[hi]!.wordId }
}

/** Extend a selection by one word in `direction` (keyboard shift-arrow), moving the focus
 * end only -- the anchor stays put, matching native text-selection behaviour. */
export function extendSelection(flat: FlatWord[], selection: Selection, direction: -1 | 1): Selection {
  const focusIdx = flat.findIndex((w) => w.wordId === selection.focusWordId)
  if (focusIdx === -1) return selection
  const nextIdx = Math.max(0, Math.min(flat.length - 1, focusIdx + direction))
  const next = flat[nextIdx]
  if (!next) return selection
  return { anchorWordId: selection.anchorWordId, focusWordId: next.wordId }
}

/** The distinct, order-preserved passage ids a selection range covers (used by "derive short
 * from selection" -- `derive_cut` operates on whole passages, so a word range is widened to
 * every passage it touches). Words in a `gap` block (kind "gap", no passage) are skipped. */
export function passageIdsInRange(flat: FlatWord[], range: { startWordId: string; endWordId: string }): string[] {
  const startIdx = flat.findIndex((w) => w.wordId === range.startWordId)
  const endIdx = flat.findIndex((w) => w.wordId === range.endWordId)
  if (startIdx === -1 || endIdx === -1) return []
  const ids: string[] = []
  const seen = new Set<string>()
  for (let i = startIdx; i <= endIdx; i++) {
    const pid = flat[i]!.passageId
    if (pid && !seen.has(pid)) {
      seen.add(pid)
      ids.push(pid)
    }
  }
  return ids
}

/** True if the selection's whole range shares one sync group (the only ranges a single
 * `delete_words`/`move_words`/etc. op can address). Multi-sync-group selections are
 * rejected by the caller before an op is attempted. */
export function selectionSyncGroup(flat: FlatWord[], range: { startWordId: string; endWordId: string }): string | null {
  const startIdx = flat.findIndex((w) => w.wordId === range.startWordId)
  const endIdx = flat.findIndex((w) => w.wordId === range.endWordId)
  if (startIdx === -1 || endIdx === -1) return null
  const group = flat[startIdx]!.syncGroupId
  for (let i = startIdx; i <= endIdx; i++) {
    if (flat[i]!.syncGroupId !== group) return null
  }
  return group
}
