import type { IngestSource, TranscribeEstimate, TranscribeJob } from '../api/types'
import type { ConfirmSpend, SpendSummary } from '../enrich/spend'
import { createBudget, getTranscribeEstimate, IngestApiError, startTranscription } from './api'
import type { IngestEvent } from './steps'

/** T35: transcription spends money (Deepgram, `usd`), so it goes through the same one confirm
 * as every other spend (T31): price it, show "≈ X usd", and only on Confirm create ONE budget
 * capped at exactly that amount and queue the job naming it. The core refuses anything past
 * the cap. */

export function transcribeWorkflow(syncGroupId: string): string {
  return `transcribe-${syncGroupId}`
}

function minutesText(minutes: number): string {
  return minutes >= 10 ? `${Math.round(minutes)}` : minutes.toFixed(1)
}

export function transcribeSummary(name: string, estimate: TranscribeEstimate): SpendSummary {
  if (estimate.amount == null) throw new IngestApiError(0, `${name} has no cost estimate, so it won't be transcribed: nothing spends blind.`)
  return {
    nodeIds: ['transcribe'],
    amount: estimate.amount,
    unit: estimate.unit,
    label: `${minutesText(estimate.minutes)} min of audio (Deepgram)`,
    title: `Transcribe ${name}?`,
  }
}

export async function transcribeWithConfirm(
  pid: string, source: Pick<IngestSource, 'name' | 'sync_group_id'>, confirm: ConfirmSpend, now: () => number = Date.now,
): Promise<{ cancelled: true } | TranscribeJob> {
  const summary = transcribeSummary(source.name, await getTranscribeEstimate(pid, source.sync_group_id))
  if (!(await confirm(summary))) return { cancelled: true }
  const budgetId = `${transcribeWorkflow(source.sync_group_id)}-${now()}`
  await createBudget(pid, budgetId, summary.amount, summary.unit)
  return startTranscription(pid, source.sync_group_id, budgetId)
}

export interface TranscribeProgress {
  label: string | null
  percent: number | null
  result: { ok: boolean; detail: string } | null
}

/** Pure: one transcription job's events (`job_worker.py`: step / progress / cost / result). */
export function foldTranscribe(events: IngestEvent[]): TranscribeProgress {
  const out: TranscribeProgress = { label: null, percent: null, result: null }
  for (const { kind, event } of events) {
    if ((kind === 'step' || kind === 'progress') && typeof event.label === 'string') out.label = event.label
    if (kind === 'step') out.percent = null
    if (kind === 'progress' && typeof event.i === 'number' && typeof event.n === 'number' && event.n > 0) {
      out.percent = Math.round((event.i / event.n) * 100)
    }
    if (kind === 'result') out.result = { ok: event.ok === true, detail: typeof event.detail === 'string' ? event.detail : '' }
  }
  return out
}
