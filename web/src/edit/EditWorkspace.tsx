import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useCutStore } from '../store/cutStore'
import { WorkspaceGraphPanel } from '../enrich/WorkspaceGraphPanel'
import { buildBlocks, flattenBlocks } from './blocks'
import { extendSelection, orderedRange, passageIdsInRange, selectionSyncGroup } from './selection'
import { Monitor } from './monitor/Monitor'
import { frameToWordId, wordIdToFrame } from './monitor/frameWord'
import { isNoMediaCut } from './sections'
import { RawTranscript } from './transcript/RawTranscript'
import { SelectionToolbar } from './transcript/SelectionToolbar'
import { SuggestionsBar } from './transcript/SuggestionsBar'
import { TranscriptView } from './transcript/TranscriptView'

// T30e (owner click-through, item b): the pre-lock media-backed editing tools (TranscriptView
// + amber SuggestionsBar + Monitor) are parked in favor of the post-lock RawTranscript
// workspace (docs/TASKS.md: T13a "parked: pre-lock path") -- gated behind this flag so they
// can never appear by accident. Read once at module scope: an env var, not runtime state.
const PRE_LOCK_TOOLS_ENABLED = import.meta.env.VITE_PRE_LOCK_TOOLS === '1'

export function EditWorkspace() {
  const { pid, cutId } = useParams<{ pid: string; cutId: string }>()
  const cut = useCutStore((s) => s.cut)
  const revision = useCutStore((s) => s.revision)
  const loading = useCutStore((s) => s.loading)
  const conflict = useCutStore((s) => s.conflict)
  const unreachable = useCutStore((s) => s.unreachable)
  const contextLoaded = useCutStore((s) => s.contextLoaded)
  const wordIndexBySyncGroup = useCutStore((s) => s.wordIndexBySyncGroup)
  const showCuts = useCutStore((s) => s.showCuts)
  const setShowCuts = useCutStore((s) => s.setShowCuts)
  const selection = useCutStore((s) => s.selection)
  const setSelection = useCutStore((s) => s.setSelection)
  const shoots = useCutStore((s) => s.shoots)
  const sourcesById = useCutStore((s) => s.sourcesById)
  const suggestions = useCutStore((s) => s.suggestions)
  const syncGroupToTranscript = useCutStore((s) => s.syncGroupToTranscript)
  const loadSuggestions = useCutStore((s) => s.loadSuggestions)
  const loadProjectContext = useCutStore((s) => s.loadProjectContext)
  const loadCut = useCutStore((s) => s.loadCut)
  const applyOp = useCutStore((s) => s.applyOp)
  const undo = useCutStore((s) => s.undo)
  const redo = useCutStore((s) => s.redo)
  const timeline = useCutStore((s) => s.timeline)
  const [playFrame, setPlayFrame] = useState(0)
  const [seekFrame, setSeekFrame] = useState<number | undefined>(undefined)
  const [seekToken, setSeekToken] = useState(0)

  useEffect(() => {
    // Sequenced on purpose: `loadCut` resolves `sync_group_id -> transcript_id` from the
    // context `loadProjectContext` fetches, so it must not start first (a race would leave
    // the transcript pane empty if the cut's own fetch happened to resolve first).
    if (!pid || !cutId) return
    void loadProjectContext(pid).then(() => loadCut(pid, cutId))
  }, [pid, cutId, loadProjectContext, loadCut])

  useEffect(() => {
    const firstTranscriptId = [...syncGroupToTranscript.values()][0]
    if (firstTranscriptId) void loadSuggestions(firstTranscriptId)
  }, [syncGroupToTranscript, loadSuggestions])

  const blocks = useMemo(() => (cut ? buildBlocks(cut, wordIndexBySyncGroup) : []), [cut, wordIndexBySyncGroup])
  const allWords = useMemo(() => flattenBlocks(blocks, wordIndexBySyncGroup), [blocks, wordIndexBySyncGroup])
  const visibleWords = useMemo(() => (showCuts ? allWords : allWords.filter((w) => !w.deleted)), [allWords, showCuts])

  // T23: a cut whose every passage plays a `kind: "virtual"` source has no media at all --
  // Post shows the transcript only (no monitor, no waveform, no seek).
  const sourceKindById = useMemo(() => {
    const m = new Map<string, string>()
    for (const [id, source] of sourcesById) m.set(id, source.kind)
    return m
  }, [sourcesById])
  const noMedia = useMemo(() => (cut ? isNoMediaCut(cut, sourceKindById) : false), [cut, sourceKindById])

  const currentWordId = useMemo(
    () => frameToWordId(timeline, playFrame, wordIndexBySyncGroup),
    [timeline, playFrame, wordIndexBySyncGroup],
  )

  const range = selection ? orderedRange(allWords, selection) : null
  const rangeSyncGroup = range ? selectionSyncGroup(allWords, range) : null
  const rangePassageIds = useMemo(() => (range ? passageIdsInRange(allWords, range) : []), [allWords, range])
  const rangeHasDeleted = useMemo(() => {
    if (!range) return false
    const startIdx = allWords.findIndex((w) => w.wordId === range.startWordId)
    const endIdx = allWords.findIndex((w) => w.wordId === range.endWordId)
    if (startIdx === -1 || endIdx === -1) return false
    return allWords.slice(startIdx, endIdx + 1).some((w) => w.deleted)
  }, [allWords, range])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        if (e.shiftKey) void redo()
        else void undo()
        return
      }
      if (!selection) return
      if (e.key === 'ArrowLeft' && e.shiftKey) {
        e.preventDefault()
        setSelection(extendSelection(visibleWords, selection, -1))
      } else if (e.key === 'ArrowRight' && e.shiftKey) {
        e.preventDefault()
        setSelection(extendSelection(visibleWords, selection, 1))
      } else if ((e.key === 'Backspace' || e.key === 'Delete') && range && rangeSyncGroup) {
        e.preventDefault()
        void applyOp('delete_words', { sync_group_id: rangeSyncGroup, start_word_id: range.startWordId, end_word_id: range.endWordId })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selection, visibleWords, range, rangeSyncGroup, setSelection, applyOp, undo, redo])

  function angleLabelFor(sourceId: string | null): string | null {
    if (!sourceId) return null
    const source = sourcesById.get(sourceId)
    return source ? `${source.role} · ${sourceId.slice(0, 6)}` : sourceId.slice(0, 6)
  }

  function handleMove(beforeWordId: string | null) {
    if (!range || !rangeSyncGroup) return
    const beforeWord = beforeWordId
      ? (() => {
          const w = allWords.find((x) => x.wordId === beforeWordId)
          return w ? { transcript_id: syncGroupToTranscript.get(w.syncGroupId) ?? '', word_id: beforeWordId } : null
        })()
      : null
    void applyOp('move_words', {
      sync_group_id: rangeSyncGroup, start_word_id: range.startWordId, end_word_id: range.endWordId,
      before_word: beforeWord,
    })
  }

  if (!pid || !cutId) return null

  // T30e (owner click-through, item c): a network-level failure (post_api not reachable at
  // all) is distinct from any ordinary load error -- show this instead of an empty page or
  // guessing at a layout, and never fall through to either transcript workspace below.
  if (unreachable) {
    return (
      <div className="flex-1 flex items-center justify-center text-neutral-500" data-testid="backend-unreachable">
        Post&apos;s backend isn&apos;t running.
      </div>
    )
  }

  // T30e (owner click-through, item b): `noMedia` defaults to `false` while `cut`/sources are
  // still loading, which used to pick the media-backed layout by default and flash it before
  // flipping to RawTranscript once the real data landed. Wait for both before choosing.
  if (!contextLoaded || !cut) {
    return <div className="flex-1 flex items-center justify-center text-neutral-500" data-testid="workspace-loading">Loading…</div>
  }

  // T24: the post-picture-lock raw transcript is a whole different, much simpler workspace --
  // no monitor, no show-cuts toggle, no legacy word-op toolbar, no suggestions bar. It owns
  // its own two-pane (reading surface + Visuals rail) layout end to end. T30e: also the
  // fallback whenever the pre-lock tools flag is off, media cut or not (see
  // `PRE_LOCK_TOOLS_ENABLED` above).
  if (noMedia || !PRE_LOCK_TOOLS_ENABLED) {
    return (
      <div className="flex flex-col flex-1 min-h-0">
        <div className="flex items-center gap-3 px-3 py-1.5 border-b border-neutral-200 dark:border-neutral-800">
          {loading && <span data-testid="loading" className="text-neutral-500">Loading…</span>}
          {conflict && (
            <span data-testid="conflict-banner" className="text-red-600">
              This cut changed elsewhere — refreshed to the latest version.
            </span>
          )}
        </div>
        <RawTranscript cut={cut} words={visibleWords} />
        <WorkspaceGraphPanel />
        {revision !== null && <span data-testid="revision" className="hidden">{revision}</span>}
      </div>
    )
  }

  return (
    <div className="flex flex-1 min-h-0">
      <div className="flex-1 min-w-0 flex flex-col border-r border-neutral-200 dark:border-neutral-800">
        <div className="flex items-center gap-3 px-3 py-1.5 border-b border-neutral-200 dark:border-neutral-800">
          {loading && <span data-testid="loading" className="text-neutral-500">Loading…</span>}
          {conflict && (
            <span data-testid="conflict-banner" className="text-red-600">
              This cut changed elsewhere — refreshed to the latest version.
            </span>
          )}
          <label className="ml-auto flex items-center gap-1">
            <input
              type="checkbox"
              data-testid="show-cuts-toggle"
              checked={showCuts}
              onChange={(e) => setShowCuts(e.target.checked)}
            />
            Show cuts
          </label>
        </div>
        <SuggestionsBar suggestions={suggestions} />
        <div className="relative flex-1 min-h-0 flex flex-col">
          {/* Fixed-height slot, always in the layout (not conditionally mounted): if the
              toolbar's first appearance pushed the transcript down instead, that reflow would
              happen between the mousedown that creates a selection and its matching mouseup,
              so a real click's mouseup could land on a different (shifted) word than the one
              pressed -- and a same-element mouseup is required for the browser to fire
              `click` at all, which "click a word to seek" depends on. */}
          <div className="h-9 px-3 pt-1 shrink-0">
            {range && rangeSyncGroup && (
              <SelectionToolbar
                pid={pid}
                syncGroupId={rangeSyncGroup}
                startWordId={range.startWordId}
                endWordId={range.endWordId}
                hasDeletedWordsInRange={rangeHasDeleted}
                shoots={shoots}
                passageIds={rangePassageIds}
              />
            )}
          </div>
          <TranscriptView
            words={visibleWords}
            selection={selection}
            currentWordId={currentWordId}
            angleLabelFor={angleLabelFor}
            onSelectionChange={setSelection}
            onWordClick={(wordId) => {
              setSelection({ anchorWordId: wordId, focusWordId: wordId })
              const word = allWords.find((w) => w.wordId === wordId)
              if (!word) return
              const frame = wordIdToFrame(timeline, wordIndexBySyncGroup, word.syncGroupId, wordId)
              if (frame !== null) {
                setSeekFrame(frame)
                setSeekToken((t) => t + 1)
              }
            }}
            onMove={handleMove}
          />
        </div>
      </div>
      <div className="w-[420px] shrink-0 flex flex-col">
        <Monitor pid={pid} seekFrame={seekFrame} seekToken={seekToken} onFrame={setPlayFrame} />
        <div data-testid="visuals-placeholder" className="flex-1 border-t border-neutral-200 dark:border-neutral-800 p-3 text-neutral-400">
          Visuals (T13)
        </div>
      </div>
      <WorkspaceGraphPanel />
      {revision !== null && <span data-testid="revision" className="hidden">{revision}</span>}
    </div>
  )
}
