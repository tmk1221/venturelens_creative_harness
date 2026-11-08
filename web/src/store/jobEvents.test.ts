import { describe, expect, it } from 'vitest'
import { applyJobEvent, jobTitle, type JobEvent, type JobView } from './jobEvents'

const ev = (seq: number, kind: string, event: Record<string, unknown> = {}): JobEvent =>
  ({ job_id: 'j', workflow_id: 'transcribe-sg', seq, kind, at: seq, event: { kind, ...event } })

function fold(events: JobEvent[]): JobView | undefined {
  return events.reduce<JobView | undefined>((prev, e) => applyJobEvent(prev, e), undefined)
}

describe('applyJobEvent', () => {
  it('keeps the step label and upload percent until the job ends', () => {
    const job = fold([ev(0, 'step', { label: 'Uploading the audio to Deepgram' }), ev(1, 'progress', { i: 3, n: 4 })])!
    expect([job.label, job.percent, job.kind]).toEqual(['Uploading the audio to Deepgram', 75, 'progress'])
    const done = applyJobEvent(job, ev(2, 'result', { ok: false, detail: 'Deepgram answered HTTP 401: bad key' }))
    expect(done.result).toEqual({ ok: false, detail: 'Deepgram answered HTTP 401: bad key' })
    expect(done.percent).toBeUndefined()
  })

  it('ignores replays and keeps a prompt sticky across later events', () => {
    const job = fold([ev(0, 'prompt', { text: 'a rooftop garden', model: 'm' }), ev(1, 'cost', { amount: 2, unit: 'credits' })])!
    expect(applyJobEvent(job, ev(1, 'progress', { i: 1, n: 2 }))).toBe(job)
    expect([job.promptText, job.promptModel, job.cost]).toEqual(['a rooftop garden', 'm', { amount: 2, unit: 'credits' }])
  })

  it('titles a job in plain words', () => {
    expect(jobTitle({ workflow_id: 'transcribe-sg1' })).toBe('Transcription')
    expect(jobTitle({ workflow_id: '_ingest' })).toBe('Getting the recording ready')
    expect(jobTitle({ workflow_id: 'wf-abc' })).toBe('Generation')
  })
})
