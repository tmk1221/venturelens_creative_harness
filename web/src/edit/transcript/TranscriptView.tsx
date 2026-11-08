import { useVirtualizer } from '@tanstack/react-virtual'
import { useMemo, useRef, useState } from 'react'
import { buildBlocks, flattenBlocks, type FlatWord } from '../blocks'
import { orderedRange } from '../selection'

const CHUNK_SIZE = 30

interface Props {
  words: FlatWord[]
  selection: { anchorWordId: string; focusWordId: string } | null
  currentWordId: string | null
  angleLabelFor: (sourceId: string | null) => string | null
  onSelectionChange: (sel: { anchorWordId: string; focusWordId: string } | null) => void
  onWordClick: (wordId: string) => void
  /** Drag a selected range onto a drop caret between words. `beforeWordId: null` means "end
   * of the transcript". */
  onMove: (beforeWordId: string | null) => void
}

export function chunkWords(words: FlatWord[], size = CHUNK_SIZE): FlatWord[][] {
  const chunks: FlatWord[][] = []
  for (let i = 0; i < words.length; i += size) chunks.push(words.slice(i, i + size))
  return chunks
}

export function TranscriptView({
  words,
  selection,
  currentWordId,
  angleLabelFor,
  onSelectionChange,
  onWordClick,
  onMove,
}: Props) {
  const parentRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)
  const dragMovedRef = useRef(false)
  const gestureAnchorRef = useRef<string | null>(null)
  const [dropBeforeWordId, setDropBeforeWordId] = useState<string | null | 'end'>(null)
  // Selection settled at the end of the last completed mouse gesture, as opposed to
  // `selection` itself which updates live on every mousedown/mouseenter. `draggable` below
  // is computed from THIS, not from the live selection: if a word became draggable
  // synchronously within the same mousedown/mouseup that first selected it, Chromium
  // interprets the draggable-attribute flip mid-gesture as a native drag start and swallows
  // the `click` that would otherwise follow -- silently breaking "click a word to seek". A
  // plain click (mousedown+mouseup on the same word, no motion in between) only commits from
  // the word's own `onClick`, which runs strictly after that `click` has already been
  // dispatched, so it can never retroactively suppress it. A real drag-select (mouseenter
  // fires on a different word before mouseup) commits on `mouseup` instead, since a
  // cross-element mouseup never produces a native `click` in the first place -- nothing to
  // suppress. Gating draggable on the *previous* gesture's outcome also matches the intended
  // UX (select, then drag the selection): a fresh click always selects and seeks; dragging a
  // range needs a second press once it's already selected.
  const [committedSelection, setCommittedSelection] = useState<typeof selection>(null)
  const chunks = useMemo(() => chunkWords(words), [words])

  const range = selection ? orderedRange(words, selection) : null
  const selectedIds = useMemo(() => {
    if (!range) return null
    const startIdx = words.findIndex((w) => w.wordId === range.startWordId)
    const endIdx = words.findIndex((w) => w.wordId === range.endWordId)
    if (startIdx === -1 || endIdx === -1) return null
    return new Set(words.slice(startIdx, endIdx + 1).map((w) => w.wordId))
  }, [words, range])

  const committedRange = committedSelection ? orderedRange(words, committedSelection) : null
  const draggableIds = useMemo(() => {
    if (!committedRange) return null
    const startIdx = words.findIndex((w) => w.wordId === committedRange.startWordId)
    const endIdx = words.findIndex((w) => w.wordId === committedRange.endWordId)
    if (startIdx === -1 || endIdx === -1) return null
    return new Set(words.slice(startIdx, endIdx + 1).map((w) => w.wordId))
  }, [words, committedRange])

  const virtualizer = useVirtualizer({
    count: chunks.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 60,
    overscan: 8,
  })

  function handleWordDown(wordId: string, e: React.MouseEvent) {
    if (e.button !== 0) return
    draggingRef.current = true
    dragMovedRef.current = false
    gestureAnchorRef.current = wordId
    onSelectionChange({ anchorWordId: wordId, focusWordId: wordId })
  }
  function handleWordEnter(wordId: string) {
    if (!draggingRef.current || !selection) return
    if (wordId !== gestureAnchorRef.current) dragMovedRef.current = true
    onSelectionChange({ anchorWordId: selection.anchorWordId, focusWordId: wordId })
  }
  function commitGesture() {
    draggingRef.current = false
    if (dragMovedRef.current) setCommittedSelection(selection)
  }
  function handleWordClick(wordId: string) {
    onWordClick(wordId)
    setCommittedSelection({ anchorWordId: wordId, focusWordId: wordId })
  }

  return (
    <div
      ref={parentRef}
      data-testid="transcript-scroll"
      className="flex-1 overflow-y-auto p-3 leading-7"
      onMouseUp={commitGesture}
      onMouseLeave={commitGesture}
    >
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((item) => {
          const chunk = chunks[item.index]!
          return (
            <div
              key={item.key}
              data-index={item.index}
              ref={virtualizer.measureElement}
              style={{ position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${item.start}px)` }}
            >
              <div className="flex flex-wrap gap-x-1">
                {chunk.map((word) => (
                  <span key={word.wordId} className="inline-flex items-center">
                    {dropBeforeWordId === word.wordId && (
                      <span data-testid="drop-caret" className="w-0.5 h-4 bg-blue-500 mx-px" />
                    )}
                    <span
                      data-testid="word"
                      data-word-id={word.wordId}
                      data-deleted={word.deleted ? 'true' : 'false'}
                      draggable={draggableIds?.has(word.wordId) ?? false}
                      onDragStart={(e) => {
                        e.dataTransfer.effectAllowed = 'move'
                      }}
                      onDragOver={(e) => {
                        if (!selectedIds) return
                        e.preventDefault()
                        if (!selectedIds.has(word.wordId)) setDropBeforeWordId(word.wordId)
                      }}
                      onDrop={(e) => {
                        e.preventDefault()
                        if (dropBeforeWordId && dropBeforeWordId !== 'end') onMove(dropBeforeWordId)
                        setDropBeforeWordId(null)
                      }}
                      onMouseDown={(e) => handleWordDown(word.wordId, e)}
                      onMouseEnter={() => handleWordEnter(word.wordId)}
                      onClick={() => handleWordClick(word.wordId)}
                      className={[
                        'cursor-pointer rounded px-0.5 select-none',
                        word.isBlockStart ? 'border-l-2 border-neutral-300 dark:border-neutral-700 pl-1' : '',
                        word.deleted ? 'line-through text-neutral-400' : '',
                        selectedIds?.has(word.wordId) ? 'bg-blue-200 dark:bg-blue-900' : '',
                        currentWordId === word.wordId ? 'outline outline-2 outline-amber-500' : '',
                      ].join(' ')}
                      title={word.isBlockStart ? (angleLabelFor(word.angleSourceId) ?? undefined) : undefined}
                    >
                      {word.text}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <div
        data-testid="drop-zone-end"
        className="h-6"
        onDragOver={(e) => {
          e.preventDefault()
          setDropBeforeWordId('end')
        }}
        onDrop={(e) => {
          e.preventDefault()
          if (dropBeforeWordId === 'end') onMove(null)
          setDropBeforeWordId(null)
        }}
      />
    </div>
  )
}

export { buildBlocks, flattenBlocks }
