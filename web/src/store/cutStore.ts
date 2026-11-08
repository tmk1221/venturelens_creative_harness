import { create } from 'zustand'
import { api } from '../api/client'
import type { Cut, Shoot, Source, Suggestion, TimelineSegment, Word } from '../api/types'
import type { WordIndex } from '../edit/blocks'

const WORDS_PAGE = 2000

interface CutState {
  pid: string | null
  cutId: string | null
  cut: Cut | null
  revision: number | null
  loading: boolean
  error: string | null
  conflict: boolean
  /** T30e (owner click-through, "unreachable" fix): set when a network call to post_api
   * itself failed (connection refused, DNS, etc.) rather than the server answering with an
   * HTTP error -- `openapi-fetch` rethrows that case instead of populating its `error` field
   * (see the `try/catch` in `loadProjectContext`/`loadCut`). `EditWorkspace` shows "Post's
   * backend isn't running" for this, distinct from `error` (a normal failed request), and
   * never falls into either transcript layout while it's true. */
  unreachable: boolean
  /** True once `loadProjectContext` has resolved at least once for the current project --
   * `EditWorkspace`'s loading gate waits for this AND a loaded `cut` before picking a
   * transcript layout, so it never guesses the wrong one from `cut`'s still-null default. */
  contextLoaded: boolean

  shoots: Shoot[]
  sourcesById: Map<string, Source>
  syncGroupToTranscript: Map<string, string>
  wordIndexBySyncGroup: Map<string, WordIndex>
  timeline: TimelineSegment[]
  suggestions: Suggestion[]

  selection: { anchorWordId: string; focusWordId: string } | null
  showCuts: boolean

  loadProjectContext: (pid: string) => Promise<void>
  loadCut: (pid: string, cutId: string) => Promise<void>
  refetchCut: () => Promise<void>
  loadTimeline: () => Promise<void>
  loadSuggestions: (transcriptId: string) => Promise<void>
  setSelection: (sel: { anchorWordId: string; focusWordId: string } | null) => void
  setShowCuts: (v: boolean) => void
  applyOp: (name: string, args: Record<string, unknown>) => Promise<'ok' | 'conflict' | 'error'>
  undo: () => Promise<void>
  redo: () => Promise<void>
}

async function loadAllWords(pid: string, transcriptId: string): Promise<Word[]> {
  const out: Word[] = []
  let offset = 0
  for (;;) {
    const { data, error } = await api.GET('/api/projects/{pid}/transcripts/{transcript_id}/words', {
      params: { path: { pid, transcript_id: transcriptId }, query: { offset, limit: WORDS_PAGE } },
    })
    if (error || !data) break
    out.push(...data.words)
    if (data.words.length < WORDS_PAGE || out.length >= data.total) break
    offset += WORDS_PAGE
  }
  return out
}

export const useCutStore = create<CutState>((set, get) => ({
  pid: null,
  cutId: null,
  cut: null,
  revision: null,
  loading: false,
  error: null,
  conflict: false,
  unreachable: false,
  contextLoaded: false,

  shoots: [],
  sourcesById: new Map(),
  syncGroupToTranscript: new Map(),
  wordIndexBySyncGroup: new Map(),
  timeline: [],
  suggestions: [],

  selection: null,
  showCuts: false,

  loadProjectContext: async (pid) => {
    // T30e: a network-level failure (post_api not running at all) makes `api.GET` itself
    // reject -- `openapi-fetch` rethrows a fetch error rather than populating `error` --
    // distinct from a normal HTTP error response, which lands in the `if (error || !shoots)`
    // branch below as before.
    let shoots: Shoot[]
    try {
      const res = await api.GET('/api/projects/{pid}/shoots', { params: { path: { pid } } })
      if (res.error || !res.data) {
        set({ error: 'Failed to load shoots' })
        return
      }
      shoots = res.data
    } catch {
      set({ unreachable: true })
      return
    }
    const sourcesById = new Map<string, Source>()
    for (const shoot of shoots) {
      for (const source of shoot.sources) if (source.id) sourcesById.set(source.id, source)
    }

    const syncGroupToTranscript = new Map<string, string>()
    const transcriptIds = shoots.flatMap((s) => s.transcript_ids)
    await Promise.all(
      transcriptIds.map(async (tid) => {
        const { data } = await api.GET('/api/projects/{pid}/transcripts/{transcript_id}', {
          params: { path: { pid, transcript_id: tid } },
        })
        if (data) syncGroupToTranscript.set(data.transcript.sync_group_id, tid)
      }),
    )
    set({ shoots, sourcesById, syncGroupToTranscript, unreachable: false, contextLoaded: true })
  },

  loadCut: async (pid, cutId) => {
    set({ loading: true, error: null, conflict: false, pid, cutId })
    let data: { revision: number; cut: Cut } | undefined
    try {
      const res = await api.GET('/api/projects/{pid}/cuts/{cut_id}', { params: { path: { pid, cut_id: cutId } } })
      if (res.error || !res.data) {
        set({ loading: false, error: 'Failed to load cut' })
        return
      }
      data = res.data
    } catch {
      set({ loading: false, unreachable: true })
      return
    }
    if (!data) return
    set({ unreachable: false })
    const syncGroupIds = [...new Set(data.cut.passages.map((p) => p.sync_group_id))]
    const map = get().syncGroupToTranscript
    const wordIndexBySyncGroup = new Map(get().wordIndexBySyncGroup)
    await Promise.all(
      syncGroupIds.map(async (sg) => {
        if (wordIndexBySyncGroup.has(sg)) return
        const transcriptId = map.get(sg)
        if (!transcriptId) return
        const words = await loadAllWords(pid, transcriptId)
        wordIndexBySyncGroup.set(sg, { words, indexOf: new Map(words.map((w, i) => [w.id, i])) })
      }),
    )
    set({ cut: data.cut, revision: data.revision, loading: false, wordIndexBySyncGroup })
    await get().loadTimeline()
  },

  refetchCut: async () => {
    const { pid, cutId } = get()
    if (!pid || !cutId) return
    await get().loadCut(pid, cutId)
  },

  loadTimeline: async () => {
    const { pid, cutId } = get()
    if (!pid || !cutId) return
    const { data } = await api.GET('/api/projects/{pid}/cuts/{cut_id}/timeline', { params: { path: { pid, cut_id: cutId } } })
    if (data) set({ timeline: data })
  },

  loadSuggestions: async (transcriptId) => {
    const { pid } = get()
    if (!pid) return
    const { data } = await api.GET('/api/projects/{pid}/transcripts/{transcript_id}/suggestions', {
      params: { path: { pid, transcript_id: transcriptId } },
    })
    if (data) set({ suggestions: data })
  },

  setSelection: (sel) => set({ selection: sel }),
  setShowCuts: (v) => set({ showCuts: v }),

  applyOp: async (name, args) => {
    const { pid, cutId, revision } = get()
    if (!pid || !cutId || revision === null) return 'error'
    const { data, error, response } = await api.POST('/api/projects/{pid}/cuts/{cut_id}/ops', {
      params: { path: { pid, cut_id: cutId } },
      body: { name, args, expected_rev: revision },
    })
    if (response?.status === 409) {
      await get().refetchCut()
      set({ conflict: true })
      return 'conflict'
    }
    if (error || !data) {
      set({ error: `Edit failed: ${name}` })
      return 'error'
    }
    set({ selection: null })
    await get().refetchCut()
    return 'ok'
  },

  undo: async () => {
    const { pid, cutId } = get()
    if (!pid || !cutId) return
    const { error } = await api.POST('/api/projects/{pid}/cuts/{cut_id}/undo', { params: { path: { pid, cut_id: cutId } } })
    if (!error) {
      set({ selection: null })
      await get().refetchCut()
    }
  },

  redo: async () => {
    const { pid, cutId } = get()
    if (!pid || !cutId) return
    const { error } = await api.POST('/api/projects/{pid}/cuts/{cut_id}/redo', { params: { path: { pid, cut_id: cutId } } })
    if (!error) {
      set({ selection: null })
      await get().refetchCut()
    }
  },
}))
