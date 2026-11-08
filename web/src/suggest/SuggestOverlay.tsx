import { Fragment, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import type { VisualSuggestion } from '../api/types'
import './suggest.css'
import { assignLanes, lineBoxes, placeBadges, type Box } from './passageLayout'
import { kindLabel, type SuggestionWithWords } from './wordRange'

interface Props {
  /** Pending proposals with their words and badge numbers (`suggestionsWithWords`). */
  proposed: SuggestionWithWords[]
  /** T42: saved (accepted) beats -- only a numbered badge on their words, no dashed passage. */
  saved?: { id: string; n: number; wordIds: string[] }[]
  onSavedClick?: (spanId: string) => void
  /** The transcript reading surface's own element -- decorations are positioned against its
   * words' `[data-word-id]` spans, the same technique `RawTranscript.tsx` already uses for
   * its passage toolbar (`anchorRect`/`toolbarPos`). Never mutated here. */
  containerRef: RefObject<HTMLDivElement | null>
  /** T40: the suggestion whose card is hovered or focused -- its passage is drawn stronger. */
  highlightedId: string | null
  /** T40: clicking a dashed passage focuses (and scrolls to) its card in the Visuals rail. */
  onPassageClick: (id: string) => void
  accept: (id: string) => Promise<void>
  dismiss: (id: string) => Promise<void>
  /** T13b's "Adjust" action: dismisses the suggestion and hands its word range back to the
   * caller, which owns the "Add visual" dialog (RawTranscript.tsx). */
  onAdjust?: (startWordId: string, endWordId: string) => void
}

function wordBoxes(container: HTMLElement, wordIds: string[]): Box[] {
  const out: Box[] = []
  for (const id of wordIds) {
    const el = container.querySelector(`[data-word-id="${id}"]`)
    if (!el) continue
    const r = el.getBoundingClientRect()
    out.push({ top: r.top, bottom: r.bottom, left: r.left, right: r.right })
  }
  return out
}

/** Underline lanes beyond this many share the last offset (keeps them inside the line gap). */
const MAX_LANE = 3
const LANE_STEP = 4

interface Layout {
  lines: Map<string, Box[]>
  badges: Map<string, Box>
  lanes: Map<string, number>
  savedBadges: Map<string, Box>
}

/** T13b/T40/T41: the dashed passages over the transcript words (each numbered like its proposed
 * card in the Visuals rail) and the hover toolbar on them. State lives in `useSuggestRail`.
 * T41: proposals overlap, so each passage is drawn per line with its own underline lane (dashed
 * for picture, dotted for overlay) and its badge is placed clear of every other badge. Only the
 * badges take the pointer: the words under a passage stay selectable, and hovering a badge
 * lights up that passage alone. T42: saved beats get their (solid) number badge here too. */
export function SuggestOverlay({ proposed, saved = [], onSavedClick, containerRef, highlightedId, onPassageClick, accept, dismiss, onAdjust }: Props) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [badgeHoverId, setBadgeHoverId] = useState<string | null>(null)
  const [layout, setLayout] = useState<Layout>({ lines: new Map(), badges: new Map(), lanes: new Map(), savedBadges: new Map() })
  const cardRef = useRef<HTMLDivElement>(null)
  const suggestions = proposed.map((p) => p.suggestion)

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return
    const measure = () => {
      const lines = new Map<string, Box[]>()
      const anchors: { id: string; n: number; left: number; top: number }[] = []
      for (const { suggestion, wordIds, n } of proposed) {
        const boxes = lineBoxes(wordBoxes(container, wordIds))
        if (!boxes.length) continue
        lines.set(suggestion.id, boxes)
        anchors.push({ id: suggestion.id, n, left: boxes[0]!.left, top: boxes[0]!.top })
      }
      const savedKey = (id: string) => `saved:${id}`
      for (const beat of saved) {
        const first = lineBoxes(wordBoxes(container, beat.wordIds))[0]
        if (first) anchors.push({ id: savedKey(beat.id), n: beat.n, left: first.left, top: first.top })
      }
      const lanes = assignLanes(
        proposed.map((p) => ({ id: p.suggestion.id, startIndex: p.startIndex, endIndex: p.startIndex + p.wordIds.length - 1 })),
      )
      const badges = placeBadges(anchors)
      const savedBadges = new Map(saved.flatMap((b) => (badges.has(savedKey(b.id)) ? [[b.id, badges.get(savedKey(b.id))!] as const] : [])))
      setLayout({ lines, badges, lanes, savedBadges })
    }
    measure()
    // Decorations are position: fixed, so any scrolling ancestor (the transcript paper, the
    // page) moves the words under them: listen in the capture phase to catch them all.
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [containerRef, proposed, saved])

  useEffect(() => {
    if (!hoveredId) return
    function onDocClick(e: MouseEvent) {
      if (cardRef.current?.contains(e.target as Node)) return
      setHoveredId(null)
    }
    window.addEventListener('mousedown', onDocClick)
    return () => window.removeEventListener('mousedown', onDocClick)
  }, [hoveredId])

  const hovered: VisualSuggestion | undefined = suggestions.find((s) => s.id === hoveredId)
  const hoveredRect = hoveredId ? layout.lines.get(hoveredId)?.[0] : undefined
  // A hovered badge wins over the card-driven highlight, so exactly one passage lights up.
  const activeId = badgeHoverId ?? highlightedId

  return (
    <>
      {proposed.map(({ suggestion, wordIds, n }) => {
        const lines = layout.lines.get(suggestion.id)
        const badge = layout.badges.get(suggestion.id)
        if (!lines || !badge) return null
        const lane = Math.min(layout.lanes.get(suggestion.id) ?? 0, MAX_LANE)
        const overlay = suggestion.overlay_depth != null
        return (
          <div
            key={suggestion.id}
            data-testid="suggestion-decoration"
            data-suggestion-id={suggestion.id}
            data-lane={lane}
            className={`suggest-decoration${overlay ? ' is-overlay' : ''}${activeId === suggestion.id ? ' is-active' : ''}`}
          >
            {lines.map((line, i) => (
              <Fragment key={i}>
                <div className="suggest-segment" style={{ top: line.top, left: line.left, width: line.right - line.left, height: line.bottom - line.top }} />
                <div
                  className="suggest-underline"
                  data-testid="suggestion-underline"
                  style={{ top: line.bottom + 1 + lane * LANE_STEP, left: line.left, width: line.right - line.left }}
                />
              </Fragment>
            ))}
            <button
              type="button"
              className="suggest-badge suggest-passage-badge"
              data-testid="suggestion-badge"
              aria-label={`Proposal ${n}: ${wordIds.length} words`}
              style={{ top: badge.top, left: badge.left, width: badge.right - badge.left }}
              onMouseEnter={() => {
                setBadgeHoverId(suggestion.id)
                setHoveredId(suggestion.id)
              }}
              onMouseLeave={() => setBadgeHoverId(null)}
              onClick={() => {
                setHoveredId(suggestion.id)
                onPassageClick(suggestion.id)
              }}
            >
              {n}
            </button>
          </div>
        )
      })}

      {saved.map(({ id, n }) => {
        const badge = layout.savedBadges.get(id)
        if (!badge) return null
        return (
          <button
            key={`saved-${id}`}
            type="button"
            className="suggest-badge suggest-passage-badge is-saved"
            data-testid="saved-badge"
            data-span-id={id}
            aria-label={`Saved visual ${n}`}
            style={{ top: badge.top, left: badge.left, width: badge.right - badge.left }}
            onClick={() => onSavedClick?.(id)}
          >
            {n}
          </button>
        )
      })}

      {hovered && hoveredRect && (
        <div
          ref={cardRef}
          data-testid="suggestion-hover-card"
          className="suggest-hover-card"
          style={{ top: hoveredRect.bottom + 6 + MAX_LANE * LANE_STEP, left: hoveredRect.left }}
        >
          <p className="suggest-kind">{kindLabel(hovered.medium ?? 'overlay')}</p>
          <p className="suggest-brief">{hovered.brief}</p>
          <p className="suggest-rationale">{hovered.rationale}</p>
          <div className="suggest-actions">
            <button
              type="button"
              className="primary"
              data-testid="suggestion-accept"
              onClick={() => {
                void accept(hovered.id)
                setHoveredId(null)
              }}
            >
              Accept
            </button>
            <button
              type="button"
              data-testid="suggestion-adjust"
              onClick={() => {
                const start = hovered.start_word_id
                const end = hovered.end_word_id
                void dismiss(hovered.id)
                setHoveredId(null)
                onAdjust?.(start, end)
              }}
            >
              Adjust
            </button>
            <button
              type="button"
              data-testid="suggestion-dismiss"
              onClick={() => {
                void dismiss(hovered.id)
                setHoveredId(null)
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </>
  )
}
