import type { FlatWord } from '../edit/blocks'
import type { VisualSuggestion } from '../api/types'

export interface SuggestionWithWords {
  suggestion: VisualSuggestion
  wordIds: string[]
  /** T40: 1-based badge shared by the proposed card and its dashed passage, in transcript order
   * (T42: counted with the saved cards, see `numberBeats`). */
  n: number
  /** Position of the first covered word in `words` (transcript order). */
  startIndex: number
  text: string
  start: number
  end: number
}

/** Every pending suggestion whose start/end word ids both still exist in `words` (a
 * suggestion for a word range removed by an edit since the pass ran just isn't drawn --
 * it stays pending and will be picked up again once its words are back). Mirrors
 * `rawTranscript.ts::spanCards`'s own word-lookup shape, kept separate because a suggestion
 * is never a `Span`. */
export function suggestionsWithWords(words: FlatWord[], suggestions: VisualSuggestion[]): SuggestionWithWords[] {
  const index = new Map(words.map((w, i) => [w.wordId, i]))
  const out: Omit<SuggestionWithWords, 'n'>[] = []
  for (const suggestion of suggestions) {
    const a = index.get(suggestion.start_word_id)
    const b = index.get(suggestion.end_word_id)
    if (a === undefined || b === undefined || b < a) continue
    const covered = words.slice(a, b + 1)
    out.push({
      suggestion, wordIds: covered.map((w) => w.wordId), startIndex: a,
      text: covered.map((w) => w.text).join(' '), start: covered[0]!.start, end: covered[covered.length - 1]!.end,
    })
  }
  // Stable sort: ties (same start word) keep the server's order.
  return out.sort((x, y) => x.startIndex - y.startIndex).map((item, i) => ({ ...item, n: i + 1 }))
}

/** T42: one number per beat (word range) across saved cards AND proposals, in transcript order
 * (at the same start a saved card first), so a proposal keeps its number when accepted -- the
 * card it becomes sits at the same place. Saved cards on the same words (the picture and the
 * overlay one accept made) share a number; every proposal has its own.
 * Returns the proposals renumbered and span id -> number for the saved cards. */
export function numberBeats<C extends { wordIds: string[]; span: { id?: string | null } }>(
  words: FlatWord[],
  cards: C[],
  proposed: SuggestionWithWords[],
): { proposed: SuggestionWithWords[]; saved: Map<string, number> } {
  const index = new Map(words.map((w, i) => [w.wordId, i]))
  type Entry = { s: number; e: number; saved: boolean; id: string; order: number }
  const entries: Entry[] = []
  cards.forEach((card, order) => {
    const s = index.get(card.wordIds[0] ?? '')
    const e = index.get(card.wordIds[card.wordIds.length - 1] ?? '')
    if (s !== undefined && e !== undefined && card.span.id) entries.push({ s, e, saved: true, id: card.span.id, order })
  })
  proposed.forEach((p, order) => {
    entries.push({ s: p.startIndex, e: p.startIndex + p.wordIds.length - 1, saved: false, id: p.suggestion.id, order })
  })
  entries.sort((a, b) => a.s - b.s || Number(b.saved) - Number(a.saved) || a.e - b.e || a.order - b.order)
  const byKey = new Map<string, number>()
  const saved = new Map<string, number>()
  const nOf = new Map<string, number>()
  for (const entry of entries) {
    const key = entry.saved ? `${entry.s}:${entry.e}` : `proposal:${entry.id}`
    if (!byKey.has(key)) byKey.set(key, byKey.size + 1)
    ;(entry.saved ? saved : nOf).set(entry.id, byKey.get(key)!)
  }
  return { proposed: proposed.map((p) => ({ ...p, n: nOf.get(p.suggestion.id) ?? p.n })), saved }
}

/** T42: "Variant A", "Variant B", ... */
export function variantLabel(index: number): string {
  return `Variant ${String.fromCharCode(65 + index)}`
}

export type RailItem<C> = { kind: 'saved'; card: C } | { kind: 'proposed'; item: SuggestionWithWords }

/** T40: saved cards and proposed cards in one list, in transcript order; at the same start word
 * the saved card comes first. `cards` must already be in transcript order (`spanCards`). */
export function railItems<C extends { wordIds: string[] }>(words: FlatWord[], cards: C[], proposed: SuggestionWithWords[]): RailItem<C>[] {
  const index = new Map(words.map((w, i) => [w.wordId, i]))
  const out: RailItem<C>[] = []
  let p = 0
  for (const card of cards) {
    const at = index.get(card.wordIds[0] ?? '') ?? 0
    while (p < proposed.length && proposed[p]!.startIndex < at) out.push({ kind: 'proposed', item: proposed[p++]! })
    out.push({ kind: 'saved', card })
  }
  while (p < proposed.length) out.push({ kind: 'proposed', item: proposed[p++]! })
  return out
}

export const MEDIUM_OPTIONS: { value: string; label: string }[] = [
  { value: 'live_action', label: 'Live action' },
  { value: 'motion_graphic', label: 'Motion graphic' },
  { value: 'provided', label: 'Provided' },
  { value: 'aroll', label: 'A-roll' },
]

export function overlayLabel(depth: string | null | undefined, position: string | null | undefined): string | null {
  if (!depth) return null
  return `Overlay · ${depth === 'behind' ? 'behind' : 'in front'}${position ? ` · ${position}` : ''}`
}

export function kindLabel(kind: string): string {
  if (kind === 'video' || kind === 'live_action') return 'Live action'
  if (kind === 'anim' || kind === 'motion_graphic') return 'Motion graphic'
  if (kind === 'overlay') return 'Overlay'
  if (kind === 'provided') return 'Provided'
  if (kind === 'aroll') return 'A-roll'
  return kind
}
