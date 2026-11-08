/** T34: the ingest job's live step list, folded from its SSE events (`step` / `progress` /
 * `result`, see `post_core/project_new/op.py`). Pure, so replays and reconnects are harmless:
 * an event already seen (same job, same `seq`) changes nothing. */

export type StepStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed'

export interface IngestStep {
  step: string
  label: string
  status: StepStatus
  /** 0-100 while a long step (the audio extract) runs. */
  percent: number | null
  error: string | null
}

export interface IngestEvent {
  job_id: string
  seq: number
  kind: string
  event: Record<string, unknown>
}

export interface IngestRun {
  steps: IngestStep[]
  result: { ok: boolean; detail: string } | null
}

/** Every event per job id, in arrival order, without duplicates. */
export type EventsByJob = Map<string, IngestEvent[]>

export function addEvent(byJob: EventsByJob, ev: IngestEvent): EventsByJob {
  const list = byJob.get(ev.job_id) ?? []
  if (list.some((e) => e.seq === ev.seq)) return byJob
  const next = new Map(byJob)
  next.set(ev.job_id, [...list, ev].sort((a, b) => a.seq - b.seq))
  return next
}

const STATUSES: StepStatus[] = ['pending', 'running', 'done', 'skipped', 'failed']

export function foldRun(events: IngestEvent[]): IngestRun {
  const steps: IngestStep[] = []
  const byId = new Map<string, IngestStep>()
  let result: IngestRun['result'] = null
  for (const { kind, event } of events) {
    const id = typeof event.step === 'string' ? event.step : null
    if (kind === 'result') {
      result = { ok: event.ok === true, detail: typeof event.detail === 'string' ? event.detail : '' }
      continue
    }
    if (!id) continue
    let step = byId.get(id)
    if (!step) {
      step = { step: id, label: typeof event.label === 'string' ? event.label : id, status: 'pending', percent: null, error: null }
      byId.set(id, step)
      steps.push(step)
    }
    if (kind === 'step' && STATUSES.includes(event.status as StepStatus)) {
      step.status = event.status as StepStatus
      if (step.status === 'failed') step.error = typeof event.error === 'string' ? event.error : 'This step failed.'
      if (step.status === 'done' || step.status === 'skipped') step.percent = null
    } else if (kind === 'progress' && typeof event.i === 'number' && typeof event.n === 'number' && event.n > 0) {
      step.percent = Math.round((event.i / event.n) * 100)
      if (step.status === 'pending') step.status = 'running'
    }
  }
  return { steps, result }
}

/** Plain words for each status, as the step list shows them. */
export const STATUS_TEXT: Record<StepStatus, string> = {
  pending: 'Waiting',
  running: 'Working…',
  done: 'Done',
  skipped: 'Already done',
  failed: 'Failed',
}
