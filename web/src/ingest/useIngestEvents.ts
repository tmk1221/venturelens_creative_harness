import { useEffect, useRef, useState } from 'react'
import { addEvent, type EventsByJob, type IngestEvent } from './steps'

const KINDS = ['step', 'progress', 'result'] as const
const NONE: EventsByJob = new Map()

/** T34: follow the project's ingest jobs over SSE (`GET .../events?workflow=_ingest`, which
 * replays from the first event, so a reload rebuilds the whole step list). The server names
 * each SSE event after its kind, so this listens per kind -- `onmessage` only ever sees
 * unnamed events. `onResult` fires once per job when its `result` arrives. T35: `workflow`
 * follows another workflow's jobs instead, e.g. one recording's `transcribe-<sync group>`. */
export function useIngestEvents(pid: string, onResult?: (jobId: string) => void, workflow = '_ingest'): EventsByJob {
  // Keyed by project, so switching projects never shows the previous one's steps.
  const [seen, setSeen] = useState<{ pid: string; byJob: EventsByJob }>({ pid, byJob: NONE })
  const onResultRef = useRef(onResult)
  useEffect(() => {
    onResultRef.current = onResult
  })

  useEffect(() => {
    const source = new EventSource(`/api/projects/${pid}/events?workflow=${encodeURIComponent(workflow)}`)
    const finished = new Set<string>()
    const handle = (msg: MessageEvent<string>) => {
      let ev: IngestEvent
      try {
        ev = JSON.parse(msg.data) as IngestEvent
      } catch {
        return // a malformed line: ignore it, the stream keeps going
      }
      setSeen((prev) => ({ pid, byJob: addEvent(prev.pid === pid ? prev.byJob : NONE, ev) }))
      if (ev.kind === 'result' && !finished.has(ev.job_id)) {
        finished.add(ev.job_id)
        onResultRef.current?.(ev.job_id)
      }
    }
    for (const kind of KINDS) source.addEventListener(kind, handle as EventListener)
    return () => source.close()
  }, [pid, workflow])

  return seen.pid === pid ? seen.byJob : NONE
}
