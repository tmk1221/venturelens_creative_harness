import { useCallback, useMemo, useState, type ReactNode, type RefObject } from 'react'
import type { FlatWord } from '../edit/blocks'
import type { SpanCard } from '../edit/rawTranscript'
import { ProposedCard } from './ProposedCard'
import { SuggestControls } from './SuggestControls'
import { SuggestOverlay } from './SuggestOverlay'
import { useSuggestions } from './useSuggestions'
import { numberBeats, suggestionsWithWords, type SuggestionWithWords } from './wordRange'

interface Args {
  pid: string | null
  cutId: string | null
  words: FlatWord[]
  /** T42: the saved (accepted) cards -- numbered together with the proposals, badge on their words. */
  cards: SpanCard[]
  /** T42: clicking a saved card's badge on the words focuses that card. */
  onSavedFocus: (spanId: string) => void
  /** The transcript reading surface (`[data-word-id]` spans live under it). */
  containerRef: RefObject<HTMLDivElement | null>
  selection: { syncGroupId: string; startWordId: string; endWordId: string } | null
  onCutChanged: () => void
  onAdjust: (startWordId: string, endWordId: string) => void
}

/** What `VisualsRail` needs to show the suggest controls and the proposed cards. */
export interface SuggestRailProps {
  headerControls: ReactNode
  proposed: SuggestionWithWords[]
  renderProposed: (item: SuggestionWithWords) => ReactNode
  /** T42: span id -> its beat number, shown on the saved card. */
  savedNumbers: Map<string, number>
  running: boolean
  error: string | null
}

function scrollWordsIntoView(container: HTMLElement | null, wordId: string, block: ScrollLogicalPosition) {
  const el = container?.querySelector(`[data-word-id="${wordId}"]`)
  el?.scrollIntoView?.({ block, behavior: 'smooth' })
}

/** T40: one owner for the suggest pass on the raw transcript -- the pending list, which proposal
 * is hovered/focused, and the two-way pairing between a proposed card in the rail and its
 * dashed passage over the words (hover or click a card -> its words light up and scroll into
 * view; click a passage -> its card is focused and scrolled to). T42: saved and proposed beats
 * share one numbering, so an accepted card keeps its badge (on the card and on its words). Returns the overlay to mount
 * over the transcript and the props for the rail. */
export function useSuggestRail({ pid, cutId, words, cards, onSavedFocus, containerRef, selection, onCutChanged, onAdjust }: Args): {
  overlay: ReactNode
  rail: SuggestRailProps
} {
  const { suggestions, running, error, suggest, accept, dismiss, update, acceptAll, switchVariant } = useSuggestions(pid, cutId, onCutChanged)
  const { proposed, saved: savedNumbers } = useMemo(
    () => numberBeats(words, cards, suggestionsWithWords(words, suggestions)),
    [words, cards, suggestions],
  )
  // One badge on the words per saved beat (a picture and an overlay on the same words share it).
  const saved = useMemo(() => {
    const seen = new Set<number>()
    return cards.flatMap((c) => {
      const n = c.span.id ? savedNumbers.get(c.span.id) : undefined
      if (n === undefined || seen.has(n)) return []
      seen.add(n)
      return [{ id: c.span.id!, n, wordIds: c.wordIds }]
    })
  }, [cards, savedNumbers])
  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const highlightedId = hoveredId ?? focusedId

  const focusFromCard = useCallback(
    (item: SuggestionWithWords) => {
      const id = item.suggestion.id
      setFocusedId((prev) => (prev === id ? null : id))
      scrollWordsIntoView(containerRef.current, item.suggestion.start_word_id, 'center')
    },
    [containerRef],
  )
  const hoverCard = useCallback(
    (item: SuggestionWithWords, hovering: boolean) => {
      setHoveredId(hovering ? item.suggestion.id : null)
      if (hovering) scrollWordsIntoView(containerRef.current, item.suggestion.start_word_id, 'nearest')
    },
    [containerRef],
  )
  const focusFromPassage = useCallback((id: string) => {
    setFocusedId(id)
    window.requestAnimationFrame(() => {
      document.querySelector(`[data-suggestion-card-id="${id}"]`)?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
    })
  }, [])

  const overlay =
    pid && cutId ? (
      <SuggestOverlay
        proposed={proposed}
        saved={saved}
        onSavedClick={onSavedFocus}
        containerRef={containerRef}
        highlightedId={highlightedId}
        onPassageClick={focusFromPassage}
        accept={accept}
        dismiss={dismiss}
        onAdjust={onAdjust}
      />
    ) : null

  const rail: SuggestRailProps = {
    headerControls:
      pid && cutId ? (
        <SuggestControls
          running={running} error={error} pendingCount={suggestions.length} selection={selection}
          suggest={suggest} acceptAll={acceptAll}
        />
      ) : null,
    proposed,
    savedNumbers,
    renderProposed: (item) => (
      <ProposedCard
        key={item.suggestion.id}
        item={item}
        focused={focusedId === item.suggestion.id}
        dimmed={focusedId !== null && focusedId !== item.suggestion.id}
        onHover={(hovering) => hoverCard(item, hovering)}
        onFocus={() => focusFromCard(item)}
        onSave={(edits) => update(item.suggestion.id, edits)}
        onSwitchVariant={(index) => switchVariant(item.suggestion.id, index)}
        onAccept={() => accept(item.suggestion.id)}
        onDismiss={() => void dismiss(item.suggestion.id)}
      />
    ),
    running,
    error,
  }
  return { overlay, rail }
}
