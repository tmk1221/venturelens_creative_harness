import type { Span } from '../api/types'
import type { FlatWord } from './blocks'

/** T24: the raw-transcript "Add visual" picker. `overlay` is a separate layer from the rest
 * (it can coexist with a picture choice on the same words); everything else is the picture
 * layer. Mirrors `~/cc/post-transcript-first/frontend/src/transcriptSelection.js` `VISUALS`. */
export const VISUALS = [
  { id: 'aroll', layer: 'picture', title: 'Keep A-roll', detail: 'Stay with the speaker.', icon: '◎' },
  { id: 'provided', layer: 'picture', title: 'My footage', detail: 'Use a clip you already have.', icon: '▧' },
  { id: 'video', layer: 'picture', title: 'Live action', detail: 'Plan a generated B-roll shot.', icon: '▹' },
  { id: 'anim', layer: 'picture', title: 'Motion graphic', detail: 'Explain it with a full-frame graphic.', icon: '◈' },
  { id: 'overlay', layer: 'overlay', title: 'Overlay', detail: 'Add a graphic over the picture.', icon: '▱' },
] as const

export type VisualKind = (typeof VISUALS)[number]['id']

// A Span's `kind` on disk may be either naming generation VISUALS' own ids don't cover:
// T30a's PictureKind values ('live_action'/'motion_graphic'), written by `add_beat_spans`
// (the dialog/suggester-accept paths) -- as opposed to VISUALS' own ids ('video'/'anim'),
// still written by the enrich e2e fixture's raw `add_span`. Both resolve to the same label.
const KIND_ALIAS: Record<string, VisualKind> = { live_action: 'video', motion_graphic: 'anim' }

export function visualLabel(kind: string): string {
  return VISUALS.find((v) => v.id === kind)?.title ?? VISUALS.find((v) => v.id === KIND_ALIAS[kind])?.title ?? kind
}

// T30: the beat model's overlay depth/position matrix -- a TS port of
// `post_core/model/cut.py`'s `valid_overlay_positions`/`swap_position_for_depth_change` (the
// server is the real source of truth/enforcement; this is just so the dialog can grey out
// illegal combinations inline instead of round-tripping a 400). `pictureKind` here is a
// `VisualKind` id ('aroll'/'provided'/'video'/'anim'), not the server's `PictureKind` --
// `video`/`anim` behave exactly like any non-aroll picture (`_BROLL_POSITIONS`).
export type OverlayDepth = 'in_front' | 'behind'
export type OverlayPosition = 'right' | 'left' | 'lower-band' | 'full-frame' | 'center' | 'full-width'
export const BEAT_FLAGS = [
  { id: 'must_have_shot', label: 'Must-have shot' },
  { id: 'presenter_stays_on_camera', label: 'Presenter stays on camera' },
  { id: 'picture_must_match_words', label: 'Picture must match words' },
] as const

const AROLL_POSITIONS: Record<OverlayDepth, OverlayPosition[]> = {
  in_front: ['right', 'left', 'lower-band'],
  behind: ['right', 'left', 'full-frame'],
}
const BROLL_POSITIONS: OverlayPosition[] = ['right', 'left', 'lower-band', 'center', 'full-width']
const SWAP_PAIRS: Record<string, OverlayPosition> = { 'lower-band': 'full-frame', 'full-frame': 'lower-band' }

export function validOverlayPositions(pictureKind: string, depth: OverlayDepth): OverlayPosition[] {
  if (depth === 'behind') return pictureKind === 'aroll' ? AROLL_POSITIONS.behind : []
  return pictureKind === 'aroll' ? AROLL_POSITIONS.in_front : BROLL_POSITIONS
}

export function swapPositionForDepthChange(position: OverlayPosition, pictureKind: string): OverlayPosition {
  if (pictureKind !== 'aroll') return position
  return SWAP_PAIRS[position] ?? position
}

export function layerFor(kind: string): 'picture' | 'overlay' {
  return VISUALS.find((v) => v.id === kind)?.layer ?? 'picture'
}

export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds || 0))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export interface Paragraph {
  words: FlatWord[]
  /** T35: the paragraph's speaker label ('' when the transcript has none). */
  speaker: string
  /** T35: show the speaker's name above this paragraph -- a new turn, not a pause mid-turn. */
  newTurn: boolean
}

/** Break the continuous word list into paragraphs at long pauses (>= 1.5s) -- no headings, no
 * sentence-length heuristics (T24 spec: "paragraph breaks only at long pauses") -- and, T35,
 * where the speaker changes, so each turn starts with its speaker's name. */
export function paragraphs(words: FlatWord[], minPause = 1.5): Paragraph[] {
  const out: Paragraph[] = []
  let current: FlatWord[] = []
  let prev: FlatWord | null = null
  const push = () => {
    const speaker = current[0]!.speaker ?? ''
    const before = out[out.length - 1]
    out.push({ words: current, speaker, newTurn: speaker !== '' && (!before || before.speaker !== speaker) })
  }
  for (const w of words) {
    const turn = !!prev?.speaker && !!w.speaker && prev.speaker !== w.speaker
    if (current.length && prev && (w.start - prev.end >= minPause || turn)) {
      push()
      current = []
    }
    current.push(w)
    prev = w
  }
  if (current.length) push()
  return out
}

/** A Span rendered as a right-rail card, joined to its covered text/timing via the current
 * word list. Sorted in transcript order; picture spans alternate a two-tone "beat" accent
 * (matching the reference UI) so neighbouring beats read as visually distinct without
 * encoding medium/acceptance in color. Overlays never contribute to the alternation. */
export interface SpanCard {
  span: Span
  text: string
  start: number
  end: number
  wordIds: string[]
  beatTone: 0 | 1 | null
}

function wordRange(words: FlatWord[], startWordId: string, endWordId: string): FlatWord[] | null {
  const a = words.findIndex((w) => w.wordId === startWordId)
  const b = words.findIndex((w) => w.wordId === endWordId)
  if (a === -1 || b === -1 || b < a) return null
  return words.slice(a, b + 1)
}

export function spanCards(words: FlatWord[], spans: Span[]): SpanCard[] {
  const index = new Map(words.map((w, i) => [w.wordId, i]))
  let picture = 0
  return spans
    .filter((s) => !s.orphaned && index.has(s.start_anchor.word_id) && index.has(s.end_anchor.word_id))
    .sort((a, b) => index.get(a.start_anchor.word_id)! - index.get(b.start_anchor.word_id)!)
    .flatMap((span) => {
      const range = wordRange(words, span.start_anchor.word_id, span.end_anchor.word_id)
      if (!range) return []
      const card: SpanCard = {
        span,
        text: range.map((w) => w.text).join(' '),
        start: range[0]!.start,
        end: range[range.length - 1]!.end,
        wordIds: range.map((w) => w.wordId),
        beatTone: span.layer === 'picture' ? ((picture++ % 2) as 0 | 1) : null,
      }
      return [card]
    })
}

/** word id -> the cards (usually 0 or 1 picture + up to 1 overlay) that cover it. */
export function coverage(cards: SpanCard[]): Map<string, SpanCard[]> {
  const byWord = new Map<string, SpanCard[]>()
  for (const card of cards) {
    for (const id of card.wordIds) {
      if (!byWord.has(id)) byWord.set(id, [])
      byWord.get(id)!.push(card)
    }
  }
  return byWord
}

/** Which existing spans (on the same layer as `kind`) a candidate word range would overlap --
 * these must be removed before the new span is added (the store enforces no same-layer
 * overlap; see `store/invariants.py::_check_spans_no_overlap`). */
export function overlappingSpans(words: FlatWord[], spans: Span[], kind: string, startWordId: string, endWordId: string): Span[] {
  const range = wordRange(words, startWordId, endWordId)
  if (!range) return []
  const index = new Map(words.map((w, i) => [w.wordId, i]))
  const a = index.get(startWordId)!
  const b = index.get(endWordId)!
  const layer = layerFor(kind)
  return spans.filter((s) => {
    if (s.layer !== layer) return false
    const sa = index.get(s.start_anchor.word_id)
    const sb = index.get(s.end_anchor.word_id)
    if (sa === undefined || sb === undefined) return false
    return sa <= b && sb >= a
  })
}
