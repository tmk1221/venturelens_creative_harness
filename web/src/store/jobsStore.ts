import { create } from 'zustand'
import { applyJobEvent, JOB_EVENT_KINDS, type JobEvent, type JobView } from './jobEvents'

export type { JobEvent, JobView } from './jobEvents'

interface JobsState {
  jobsById: Map<string, JobView>
  connected: boolean
  source: EventSource | null
  connect: (pid: string) => void
  disconnect: () => void
}

/** The project's job events over SSE (`GET /api/projects/{pid}/events`, every workflow),
 * folded per job by `applyJobEvent`. T35 fix: listens per event kind -- the server names
 * every SSE event (`event: progress`), so a bare `onmessage` never received anything. */
export const useJobsStore = create<JobsState>((set, get) => ({
  jobsById: new Map(),
  connected: false,
  source: null,

  connect: (pid) => {
    get().source?.close()
    const source = new EventSource(`/api/projects/${pid}/events`)
    source.onopen = () => set({ connected: true })
    source.onerror = () => set({ connected: false })
    const handle = (msg: MessageEvent<string>) => {
      let payload: JobEvent
      try {
        payload = JSON.parse(msg.data) as JobEvent
      } catch {
        return // malformed event: ignore, the stream keeps going
      }
      const jobsById = new Map(get().jobsById)
      const prev = jobsById.get(payload.job_id)
      const next = applyJobEvent(prev, payload)
      if (next === prev) return
      jobsById.set(payload.job_id, next)
      set({ jobsById })
    }
    for (const kind of JOB_EVENT_KINDS) source.addEventListener(kind, handle as EventListener)
    source.onmessage = handle // an unnamed event, should a worker ever send one
    set({ source })
  },

  disconnect: () => {
    get().source?.close()
    set({ source: null, connected: false })
  },
}))
