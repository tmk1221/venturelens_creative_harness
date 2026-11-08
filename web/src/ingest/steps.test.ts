import { describe, expect, it } from 'vitest'
import { addEvent, foldRun, type EventsByJob, type IngestEvent } from './steps'

/** T34: the Ingest page's step list is a pure fold over the job's SSE events. */
function ev(seq: number, kind: string, event: Record<string, unknown>, job_id = 'j1'): IngestEvent {
  return { job_id, seq, kind, event: { kind, ...event } }
}

const PENDING = [
  ev(0, 'step', { step: 'check', label: 'Check the project folder', status: 'pending' }),
  ev(1, 'step', { step: 'audio:0', label: 'Audio for ep37.mp4', status: 'pending' }),
]

describe('foldRun', () => {
  it('lists every planned step up front, then tracks each one', () => {
    const run = foldRun([
      ...PENDING,
      ev(2, 'step', { step: 'check', label: 'Check the project folder', status: 'done' }),
      ev(3, 'step', { step: 'audio:0', label: 'Audio for ep37.mp4', status: 'running' }),
      ev(4, 'progress', { step: 'audio:0', label: 'Audio for ep37.mp4', i: 42, n: 100 }),
    ])
    expect(run.steps.map((s) => [s.step, s.status, s.percent])).toEqual([
      ['check', 'done', null],
      ['audio:0', 'running', 42],
    ])
    expect(run.result).toBeNull()
  })

  it("keeps a failure's own sentence and the job's result", () => {
    const msg = 'Audio for ep37.mp4: ffmpeg could not read the file (Invalid data).'
    const run = foldRun([
      ...PENDING,
      ev(2, 'step', { step: 'audio:0', label: 'Audio for ep37.mp4', status: 'failed', error: msg }),
      ev(3, 'result', { ok: false, detail: msg }),
    ])
    expect(run.steps[1]).toMatchObject({ status: 'failed', error: msg })
    expect(run.result).toEqual({ ok: false, detail: msg })
  })

  it('an already-done step on a re-run reads as skipped, with no stale progress', () => {
    const run = foldRun([
      ...PENDING,
      ev(2, 'progress', { step: 'audio:0', i: 10, n: 100 }),
      ev(3, 'step', { step: 'audio:0', label: 'Audio for ep37.mp4', status: 'skipped' }),
    ])
    expect(run.steps[1]).toMatchObject({ status: 'skipped', percent: null })
  })
})

describe('addEvent', () => {
  it('ignores a replayed event and keeps jobs apart', () => {
    let byJob: EventsByJob = new Map()
    for (const e of [...PENDING, PENDING[0]!, ev(0, 'step', { step: 'check', status: 'pending' }, 'j2')]) {
      byJob = addEvent(byJob, e)
    }
    expect(byJob.get('j1')).toHaveLength(2)
    expect(byJob.get('j2')).toHaveLength(1)
    const same = addEvent(byJob, PENDING[1]!)
    expect(same).toBe(byJob)
  })
})
