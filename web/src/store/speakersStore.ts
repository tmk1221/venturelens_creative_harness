import { create } from 'zustand'
import { api } from '../api/client'
import type { Speakers } from '../api/types'

interface SpeakersState {
  /** transcript id -> its speakers (label, name, words, longest-utterance sample). */
  byTranscript: Map<string, Speakers>
  /** The one speaker label whose popover is open (a `useId` of that label), if any. */
  openLabel: string | null
  setOpenLabel: (id: string | null) => void
  load: (pid: string, transcriptId: string) => Promise<void>
  /** Name one speaker on one transcript; every label for it re-renders with the new name. */
  rename: (pid: string, transcriptId: string, label: string, name: string) => Promise<void>
}

// Asked once per transcript per page load: every speaker label on the page calls `load`.
const asked = new Set<string>()

/** T35: speaker names live on the transcript (`GET/PUT .../transcripts/{tid}/speakers`), never
 * in word text, so a rename is one write and shows "everywhere" that speaker's label does. */
export const useSpeakersStore = create<SpeakersState>((set, get) => ({
  byTranscript: new Map(),
  openLabel: null,
  setOpenLabel: (id) => set({ openLabel: id }),

  load: async (pid, transcriptId) => {
    const key = `${pid}/${transcriptId}`
    if (asked.has(key)) return
    asked.add(key)
    const { data } = await api
      .GET('/api/projects/{pid}/transcripts/{transcript_id}/speakers', { params: { path: { pid, transcript_id: transcriptId } } })
      .catch(() => ({ data: undefined }))
    if (data) set({ byTranscript: new Map(get().byTranscript).set(transcriptId, data) })
  },

  rename: async (pid, transcriptId, label, name) => {
    const { data, error } = await api.PUT('/api/projects/{pid}/transcripts/{transcript_id}/speakers', {
      params: { path: { pid, transcript_id: transcriptId } },
      body: { names: { [label]: name } },
    })
    if (error || !data) {
      const detail = (error as { detail?: string; error?: string } | undefined) ?? {}
      throw new Error(detail.detail ?? detail.error ?? 'Could not rename the speaker')
    }
    set({ byTranscript: new Map(get().byTranscript).set(transcriptId, data) })
  },
}))
