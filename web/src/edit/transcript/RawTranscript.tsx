import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { Cut, Span } from '../../api/types'
import { useSuggestRail } from '../../suggest/useSuggestRail'
import { useCutStore } from '../../store/cutStore'
import { useFocusRequestStore } from '../../store/focusRequestStore'
import { useGraphPanelStore } from '../../store/graphPanelStore'
import type { FlatWord } from '../blocks'
import { clock, coverage, overlappingSpans, paragraphs, spanCards } from '../rawTranscript'
import { extendSelection, orderedRange, selectionSyncGroup } from '../selection'
import { AddVisualDialog, type BeatDraft } from './AddVisualDialog'
import { SpeakerLabel } from './SpeakerLabel'
import { useToolbarPosition } from './useToolbarPosition'
import { VisualsRail } from './VisualsRail'

interface Props {
  cut: Cut
  words: FlatWord[]
}

/** T24/T25: the post-picture-lock raw transcript workspace, its markup and CSS classes ported
 * verbatim from `~/cc/post-transcript-first/frontend/src/{Transcript.jsx,VisualRail.jsx}` (see
 * `web/src/legacy-look.css`, copied unchanged from that app's `styles.css`). Speech on the left
 * as one continuous reading surface (paragraph breaks only at long pauses), "Visuals" on the
 * right. The only actions are "Add visual" (opens the "What should we see here?" dialog) and
 * "Remove"; no suggestions, no fillers/silences bar, no show-cuts toggle, no section headers,
 * no monitor -- T24's reduced scope, kept as-is for T25. */
export function RawTranscript({ cut, words }: Props) {
  const applyOp = useCutStore((s) => s.applyOp)
  const pid = useCutStore((s) => s.pid)
  const refetchCut = useCutStore((s) => s.refetchCut)
  const syncGroupToTranscript = useCutStore((s) => s.syncGroupToTranscript)
  const [selection, setSelection] = useState<{ anchorWordId: string; focusWordId: string } | null>(null)
  const [dialogFor, setDialogFor] = useState<{ startWordId: string; endWordId: string } | null>(null)
  const [focusedSpanId, setFocusedSpanId] = useState<string | null>(null)
  const openGraph = useGraphPanelStore((s) => s.openGraph)
  const draggingRef = useRef(false)
  // The toolbar waits for the mouse to be released: it never appears mid-drag.
  const [mouseDown, setMouseDown] = useState(false)
  const textRef = useRef<HTMLDivElement>(null)
  const toolbarRef = useRef<HTMLDivElement>(null)

  const groups = useMemo(() => paragraphs(words), [words])
  const cards = useMemo(() => spanCards(words, cut.spans), [words, cut.spans])
  const cov = useMemo(() => coverage(cards), [cards])
  const focusedCard = cards.find((c) => c.span.id === focusedSpanId) ?? null
  const focusedWordIds = useMemo(() => new Set(focusedCard?.wordIds ?? []), [focusedCard])
  const beatMarks = useMemo(() => {
    // word id -> (its picture card, isStart, isEnd) -- the alternating-tint "beat" the
    // reading surface paints, distinct from an overlay's dotted underline.
    const marks = new Map<string, { card: (typeof cards)[number]; start: boolean; end: boolean }>()
    const pictureCovered = new Map<string, (typeof cards)[number]>()
    for (const c of cards) if (c.span.layer === 'picture') for (const id of c.wordIds) pictureCovered.set(id, c)
    for (let i = 0; i < words.length; i++) {
      const card = pictureCovered.get(words[i]!.wordId)
      if (!card) continue
      const prev = pictureCovered.get(words[i - 1]?.wordId ?? '')
      const next = pictureCovered.get(words[i + 1]?.wordId ?? '')
      marks.set(words[i]!.wordId, { card, start: prev?.span.id !== card.span.id, end: next?.span.id !== card.span.id })
    }
    return marks
  }, [words, cards])

  const cutId = cut.id
  const range = selection ? orderedRange(words, selection) : null
  const rangeSyncGroupId = range ? selectionSyncGroup(words, range) : null
  const activeIds = useMemo(() => {
    if (!range) return null
    const a = words.findIndex((w) => w.wordId === range.startWordId)
    const b = words.findIndex((w) => w.wordId === range.endWordId)
    if (a === -1 || b === -1) return null
    return new Set(words.slice(a, b + 1).map((w) => w.wordId))
  }, [words, range])
  const selectedText = useMemo(() => {
    if (!range || !activeIds) return null
    const inRange = words.filter((w) => activeIds.has(w.wordId))
    if (!inRange.length) return null
    return { text: inRange.map((w) => w.text).join(' '), start: inRange[0]!.start, end: inRange[inRange.length - 1]!.end, count: inRange.length }
  }, [words, range, activeIds])

  // T27/T30e: selection-anchored positioning lives in `useToolbarPosition` (split out under
  // the line budget) -- floats the passage toolbar next to the current selection.
  const toolbarPos = useToolbarPosition(textRef, toolbarRef, range, selectedText)

  function handleWordDown(wordId: string) {
    // Our word-level highlight is the selection; never let the browser paint its own on top.
    window.getSelection()?.removeAllRanges()
    draggingRef.current = true
    setMouseDown(true)
    setSelection({ anchorWordId: wordId, focusWordId: wordId })
  }
  function handleWordEnter(wordId: string) {
    if (!draggingRef.current || !selection) return
    setSelection({ anchorWordId: selection.anchorWordId, focusWordId: wordId })
  }
  function handleWordDoubleClick(wordId: string) {
    // Explicit selection, independent of the browser's native double-click word-select --
    // the custom drag/click selection model above never reads `window.getSelection()`.
    setSelection({ anchorWordId: wordId, focusWordId: wordId })
  }
  // Escape dismisses the toolbar even when focus has moved onto one of its own buttons
  // (outside the transcript region's own onKeyDown, which only fires while it has focus).
  useLayoutEffect(() => {
    if (!selection) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setSelection(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selection])

  function handleWordClick(wordId: string) {
    const matching = cov.get(wordId) ?? []
    const chosen = matching.find((c) => c.span.id === focusedSpanId) ?? matching[0]
    setFocusedSpanId(chosen?.span.id ?? null)
  }

  const dialogRange = dialogFor
    ? (() => {
        const a = words.findIndex((w) => w.wordId === dialogFor.startWordId)
        const b = words.findIndex((w) => w.wordId === dialogFor.endWordId)
        if (a === -1 || b === -1) return null
        const inRange = words.slice(a, b + 1)
        return { text: inRange.map((w) => w.text).join(' '), start: inRange[0]!.start, end: inRange[inRange.length - 1]!.end, count: inRange.length }
      })()
    : null
  const editingSpan: Span | null = dialogFor
    ? (cut.spans.find(
        (s) => !s.orphaned && s.layer === 'picture' && s.start_anchor.word_id === dialogFor.startWordId && s.end_anchor.word_id === dialogFor.endWordId,
      ) ?? null)
    : null
  const editingOverlaySpan: Span | null = dialogFor
    ? (cut.spans.find(
        (s) => !s.orphaned && s.layer === 'overlay' && s.start_anchor.word_id === dialogFor.startWordId && s.end_anchor.word_id === dialogFor.endWordId,
      ) ?? null)
    : null
  const dialogSyncGroupId = dialogFor ? selectionSyncGroup(words, dialogFor) : null
  const suggestCtx = pid && cutId && dialogFor && dialogSyncGroupId
    ? { pid, cutId, syncGroupId: dialogSyncGroupId, startWordId: dialogFor.startWordId, endWordId: dialogFor.endWordId }
    : null

  // T30e: the top-bar Decisions panel asks this transcript to focus/highlight a beat's card
  // (opening its graph, for a node-level decision, is a separate workspace-level concern --
  // `graphPanelStore`, set directly by the Decisions panel itself).
  const focusRequest = useFocusRequestStore((s) => s.request)
  const clearFocusRequest = useFocusRequestStore((s) => s.clearFocusRequest)
  useEffect(() => {
    if (!focusRequest) return
    setFocusedSpanId(focusRequest.spanId)
    clearFocusRequest()
  }, [focusRequest, clearFocusRequest])

  // T30c: "Save"/"Open in graph" both replace whatever picture/overlay spans currently sit
  // on these anchors (this dialog's own edit, plus anything else overlapping either layer)
  // with fresh ones sharing the full beat model, in one atomic `add_beat_spans` op -- the
  // same "accept creates both layers" shape T13b's suggester accept uses server-side.
  async function applyBeat(beat: BeatDraft): Promise<Span | null> {
    if (!dialogFor || !dialogSyncGroupId) return null
    if (beat.pictureKind === null && beat.overlay === null) return null
    const pictureConflicts = beat.pictureKind
      ? overlappingSpans(words, cut.spans, 'video', dialogFor.startWordId, dialogFor.endWordId).filter((s) => s.id !== editingSpan?.id)
      : []
    const overlayConflicts = beat.overlay
      ? overlappingSpans(words, cut.spans, 'overlay', dialogFor.startWordId, dialogFor.endWordId).filter((s) => s.id !== editingOverlaySpan?.id)
      : []
    for (const conflict of [...pictureConflicts, ...overlayConflicts]) {
      // eslint-disable-next-line no-await-in-loop -- ops must land in order, each against the latest revision
      await applyOp('remove_span', { span_id: conflict.id })
    }
    if (editingSpan) await applyOp('remove_span', { span_id: editingSpan.id })
    if (editingOverlaySpan) await applyOp('remove_span', { span_id: editingOverlaySpan.id })
    await applyOp('add_beat_spans', {
      sync_group_id: dialogSyncGroupId, start_word_id: dialogFor.startWordId, end_word_id: dialogFor.endWordId,
      picture_kind: beat.pictureKind, brief_text: beat.brief, direction_note: beat.directionNote,
      flags: beat.flags, overlay_depth: beat.overlay?.depth ?? null, overlay_position: beat.overlay?.position ?? null,
      provenance: 'human',
    })
    const fresh = useCutStore.getState().cut
    return (
      fresh?.spans.find(
        (s) => !s.orphaned && s.layer === (beat.pictureKind ? 'picture' : 'overlay')
          && s.start_anchor.word_id === dialogFor.startWordId && s.end_anchor.word_id === dialogFor.endWordId,
      ) ?? null
    )
  }

  async function saveVisual(beat: BeatDraft) {
    await applyBeat(beat)
    setDialogFor(null)
    setSelection(null)
  }

  // T30c dialog exit #2, race fixed T30e: open the workspace-level graph on the new/edited
  // span's id (and, for a motion-graphic's own written brief, its `brief.write` node id).
  // This used to also call `ensureSpanWorkflow` itself here -- but the freshly-mounted card's
  // own `useWorkflow` hook makes that *same* idempotent call on mount, and both calls raced
  // to write the new `workflow_id` back onto the cut: whichever lost got a 409, silently
  // swallowed, so the graph never opened. One call now (the card's own): `beat.pictureKind`
  // alone tells us the focus node, no round trip needed.
  async function openInGraph(beat: BeatDraft) {
    const span = await applyBeat(beat)
    setDialogFor(null)
    setSelection(null)
    if (!span?.id) return
    setFocusedSpanId(span.id)
    openGraph(span.id, beat.pictureKind === 'motion_graphic' ? `${span.id}-brief` : undefined)
  }

  async function removeVisual() {
    if (editingSpan) await applyOp('remove_span', { span_id: editingSpan.id })
    if (editingOverlaySpan) await applyOp('remove_span', { span_id: editingOverlaySpan.id })
    setDialogFor(null)
    setSelection(null)
  }

  // T27 item 4: "Delete" directly on the card -- the old path (open "Edit", then "Remove
  // choice" inside the dialog) wasn't discoverable. Un-tints the span's words and removes it
  // in one op (one undo, via the normal cut undo stack).
  async function deleteCard(card: (typeof cards)[number]) {
    const spanId = card.span.id
    if (focusedSpanId === spanId) setFocusedSpanId(null)
    if (dialogFor && editingSpan?.id === spanId) setDialogFor(null)
    await applyOp('remove_span', { span_id: spanId })
  }

  const { overlay: suggestOverlay, rail: suggestRail } = useSuggestRail({
    pid, cutId: cutId ?? null, words, cards, containerRef: textRef,
    onSavedFocus: (spanId) => {
      setFocusedSpanId(spanId)
      document.querySelector(`[data-span-id="${spanId}"]`)?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
    },
    selection: range && rangeSyncGroupId ? { syncGroupId: rangeSyncGroupId, startWordId: range.startWordId, endWordId: range.endWordId } : null,
    onCutChanged: () => void refetchCut(),
    onAdjust: (startWordId, endWordId) => setDialogFor({ startWordId, endWordId }),
  })

  return (
    <div className="transcript-layout">
      <div className="transcript-paper">
        {/* T13b/T40: dashed proposals over the words; their cards and the Suggest controls
            live in the Visuals rail (`useSuggestRail`). */}
        {suggestOverlay}
        <p className="transcript-intro">Read the story. Select words, then “Add visual” when you want one.</p>
        <div
          ref={textRef}
          data-testid="raw-transcript"
          tabIndex={0}
          role="region"
          aria-label="Transcript"
          className="transcript-reading"
          style={{ userSelect: 'none' }}
          onMouseUp={() => {
            draggingRef.current = false
            setMouseDown(false)
          }}
          onMouseLeave={() => {
            draggingRef.current = false
            setMouseDown(false)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setSelection(null)
              return
            }
            if (!selection) return
            if (e.key === 'ArrowLeft' && e.shiftKey) {
              e.preventDefault()
              setSelection(extendSelection(words, selection, -1))
            } else if (e.key === 'ArrowRight' && e.shiftKey) {
              e.preventDefault()
              setSelection(extendSelection(words, selection, 1))
            }
          }}
        >
          {groups.map((group, gi) => {
            const transcriptId = group.newTurn ? syncGroupToTranscript.get(group.words[0]!.syncGroupId) : undefined
            return (
              <Fragment key={gi}>
                {pid && transcriptId && <SpeakerLabel pid={pid} transcriptId={transcriptId} label={group.speaker} />}
                <p className="transcript-paragraph">
                  {group.words.map((word) => {
                    const beat = beatMarks.get(word.wordId)
                    const planned = cov.get(word.wordId) ?? []
                    const hasPicture = planned.some((c) => c.span.layer === 'picture')
                    const hasOverlay = planned.some((c) => c.span.layer === 'overlay')
                    const selected = activeIds?.has(word.wordId) ?? false
                    const cardFocused = focusedWordIds.has(word.wordId)
                    return (
                      <span
                        key={word.wordId}
                        data-testid="word"
                        data-word-id={word.wordId}
                        onMouseDown={() => handleWordDown(word.wordId)}
                        onMouseEnter={() => handleWordEnter(word.wordId)}
                        onClick={() => handleWordClick(word.wordId)}
                        onDoubleClick={() => handleWordDoubleClick(word.wordId)}
                        className={[
                          'transcript-word',
                          selected ? 'selected' : '',
                          beat ? `beat-word beat-tone-${beat.card.beatTone}${beat.start ? ' beat-word-start' : ''}${beat.end ? ' beat-word-end' : ''}` : '',
                          !selected && cardFocused ? 'is-card-focused' : '',
                          hasPicture ? 'has-picture' : '',
                          hasOverlay ? 'has-overlay' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                      >
                        {word.text}{' '}
                      </span>
                    )
                  })}
                </p>
              </Fragment>
            )
          })}
          {words.length === 0 && <p className="sub">This transcript has no timed words yet.</p>}
        </div>
        {/* Floats next to the selection via `anchorRect`/`toolbarPos` above -- position: fixed
            (from `.transcript-selection-tools`, legacy-look.css) takes it out of document flow
            entirely, so its appearance never reflows the transcript words underneath and a
            same-element mouseup still lands on the word that was pressed. */}
        {range && selectedText && toolbarPos && !mouseDown && (
          <div
            ref={toolbarRef}
            data-testid="passage-toolbar"
            className="transcript-selection-tools"
            style={{ top: toolbarPos.top, left: toolbarPos.left }}
          >
            <div className="passage-tools-meta">
              {selectedText.count} words · {clock(selectedText.start)}–{clock(selectedText.end)}
            </div>
            <div className="passage-tools-actions">
              <button
                type="button"
                className="primary small"
                data-testid="action-add-visual"
                onClick={() => setDialogFor({ startWordId: range.startWordId, endWordId: range.endWordId })}
              >
                Add visual
              </button>
              <button type="button" className="small ghost" aria-label="Dismiss passage tools" onClick={() => setSelection(null)}>
                ×
              </button>
            </div>
          </div>
        )}
      </div>
      <aside className="transcript-inspector">
        <VisualsRail
          cards={cards}
          focusedSpanId={focusedSpanId}
          onFocus={(card) => setFocusedSpanId(card.span.id === focusedSpanId ? null : (card.span.id ?? null))}
          onClear={() => setFocusedSpanId(null)}
          onEdit={(card) => setDialogFor({ startWordId: card.span.start_anchor.word_id, endWordId: card.span.end_anchor.word_id })}
          onDelete={deleteCard}
          words={words}
          suggest={suggestRail}
        />
      </aside>
      {dialogFor && dialogRange && (
        <AddVisualDialog
          range={dialogRange}
          editing={editingSpan}
          editingOverlay={editingOverlaySpan}
          suggestCtx={suggestCtx}
          onCancel={() => setDialogFor(null)}
          onSave={saveVisual}
          onRemove={removeVisual}
          onOpenGraph={openInGraph}
        />
      )}
    </div>
  )
}
