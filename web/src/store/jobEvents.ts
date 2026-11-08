/** One SSE payload from `GET /api/projects/{pid}/events` (`post_api/routes/events.py`). */
export interface JobEvent {
  job_id: string
  workflow_id: string | null
  seq: number
  kind: string
  at: number
  event: Record<string, unknown>
}

/** What the jobs drawer shows per job, folded from its whole event stream. `kind`/`seq` are
 * the latest event's; everything else is sticky across later events, so a job's prompt
 * (T30e), its last step label and upload percent (T35) survive the events that follow. */
export interface JobView extends JobEvent {
  label?: string
  percent?: number
  cost?: { amount: number; unit: string }
  result?: { ok: boolean; detail: string }
  promptText?: string
  promptModel?: string
}

/** Every kind a worker emits (`post_core/workers/contract.py` `EVENT_KINDS`), plus the
 * runner's `stalled`. The server names each SSE event after its kind, and an `EventSource`
 * only hands named events to listeners registered for that exact name -- `onmessage` never
 * sees them, which is why the drawer used to stay empty. */
export const JOB_EVENT_KINDS = ['step', 'say', 'warn', 'err', 'progress', 'prompt', 'cost', 'artifact', 'result', 'stalled'] as const

const str = (v: unknown): string | undefined => (typeof v === 'string' ? v : undefined)

/** Pure: replays and reconnects are harmless (an event at or before the job's latest `seq`
 * changes nothing). */
export function applyJobEvent(prev: JobView | undefined, ev: JobEvent): JobView {
  if (prev && ev.seq <= prev.seq) return prev
  const e = ev.event
  const next: JobView = { ...prev, ...ev }
  const label = str(e.label)
  if ((ev.kind === 'step' || ev.kind === 'progress') && label) next.label = label
  if (ev.kind === 'step') next.percent = undefined
  if (ev.kind === 'progress' && typeof e.i === 'number' && typeof e.n === 'number' && e.n > 0) {
    next.percent = Math.round((e.i / e.n) * 100)
  }
  if (ev.kind === 'cost' && typeof e.amount === 'number') next.cost = { amount: e.amount, unit: str(e.unit) ?? '' }
  if (ev.kind === 'prompt') {
    next.promptText = str(e.text) ?? prev?.promptText
    next.promptModel = str(e.model) ?? prev?.promptModel
  }
  if (ev.kind === 'result') {
    next.result = { ok: e.ok === true, detail: str(e.detail) ?? '' }
    next.percent = undefined
  }
  return next
}

/** A job's plain-words title: what it is, not its workflow id. */
export function jobTitle(job: Pick<JobEvent, 'workflow_id'>): string {
  const wf = job.workflow_id ?? ''
  if (wf.startsWith('transcribe-')) return 'Transcription'
  if (wf === '_ingest') return 'Getting the recording ready'
  return 'Generation'
}
