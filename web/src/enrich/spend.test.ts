import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as enrichApi from './api'
import { formatEstimate, runFreeSteps, runWithSpendConfirm, SpendError, summarizeSpend } from './spend'
import type { Plan, PlanSpend } from './types'

/** T31: the plan -> confirm -> one budget -> run path every web run takes. */
vi.mock('./api', () => ({
  EnrichApiError: class EnrichApiError extends Error {
    status: number
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  },
  getPlan: vi.fn(),
  putBudget: vi.fn().mockResolvedValue({ budget: {} }),
  runWorkflow: vi.fn().mockResolvedValue({ workflow_id: 'wf1', job_ids: ['j1'], plan: {} }),
}))

function spend(node_id: string, type_id: string, amount: number | null, unit: string | null = 'credits', runnable = true): PlanSpend {
  return { node_id, type_id, amount, unit, provider: 'higgsfield', runnable }
}

function plan(spends: PlanSpend[], runnable: string[] = spends.filter((s) => s.runnable).map((s) => s.node_id)): Plan {
  return { runnable, needs_authorization: runnable, blocked_on_human: [], estimated_cost: [], spends } as unknown as Plan
}

const STILLS_AND_VIDEO = plan([
  spend('s0', 'still.generate', 1), spend('s1', 'still.generate', 1), spend('s2', 'still.generate', 1),
  spend('v', 'video.generate', 5, 'credits', false),
])

beforeEach(() => {
  vi.mocked(enrichApi.getPlan).mockReset()
  vi.mocked(enrichApi.putBudget).mockClear()
  vi.mocked(enrichApi.runWorkflow).mockClear()
})

describe('summarizeSpend', () => {
  it('counts stills/videos and sums the estimate in the plan unit, including downstream spends', () => {
    const summary = summarizeSpend(STILLS_AND_VIDEO)!
    expect(summary).toEqual({ nodeIds: ['s0', 's1', 's2', 'v'], amount: 8, unit: 'credits', label: '3 stills, 1 video' })
    expect(formatEstimate(summary)).toBe('3 stills, 1 video ≈ 8.00 credits')
  })

  it('is null when nothing spends', () => {
    expect(summarizeSpend(plan([], ['brief']))).toBeNull()
  })

  it('refuses a node with no estimate and a run mixing units', () => {
    expect(() => summarizeSpend(plan([spend('s0', 'still.generate', null, null)]))).toThrow(SpendError)
    expect(() => summarizeSpend(plan([spend('a', 'still.generate', 1), spend('b', 'x.transcribe', 1, 'usd')]))).toThrow(/mixes credits and usd/)
  })
})

describe('runWithSpendConfirm', () => {
  it('Confirm creates one budget capped at the shown estimate and one run naming exactly those nodes', async () => {
    vi.mocked(enrichApi.getPlan).mockResolvedValue(STILLS_AND_VIDEO)
    const confirm = vi.fn().mockResolvedValue(true)
    await runWithSpendConfirm('p1', 'wf1', { targets: ['s0', 's1', 's2'] }, confirm, () => 1700000000000)

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(confirm.mock.calls[0]![0].amount).toBe(8)
    expect(enrichApi.putBudget).toHaveBeenCalledTimes(1)
    expect(enrichApi.putBudget).toHaveBeenCalledWith('p1', 'wf1-1700000000000', 8, 'credits')
    expect(enrichApi.runWorkflow).toHaveBeenCalledTimes(1)
    expect(enrichApi.runWorkflow).toHaveBeenCalledWith('p1', 'wf1', {
      targets: ['s0', 's1', 's2'], budget: 'wf1-1700000000000', nodeIds: ['s0', 's1', 's2', 'v'], coversDownstream: true,
    })
  })

  it('Cancel spends nothing: no budget, no run', async () => {
    vi.mocked(enrichApi.getPlan).mockResolvedValue(STILLS_AND_VIDEO)
    const out = await runWithSpendConfirm('p1', 'wf1', { fromNode: 's0' }, vi.fn().mockResolvedValue(false))
    expect(out).toEqual({ cancelled: true })
    expect(enrichApi.putBudget).not.toHaveBeenCalled()
    expect(enrichApi.runWorkflow).not.toHaveBeenCalled()
  })

  it('a free-only run needs no confirm and names no budget', async () => {
    vi.mocked(enrichApi.getPlan).mockResolvedValue(plan([], ['brief']))
    const confirm = vi.fn()
    await runWithSpendConfirm('p1', 'wf1', { targets: ['brief'] }, confirm)
    expect(confirm).not.toHaveBeenCalled()
    expect(enrichApi.putBudget).not.toHaveBeenCalled()
    expect(enrichApi.runWorkflow).toHaveBeenCalledWith('p1', 'wf1', { targets: ['brief'] })
  })
})

describe('runFreeSteps', () => {
  it('runs only the free ready steps, never a spend', async () => {
    vi.mocked(enrichApi.getPlan).mockResolvedValue(plan([spend('v', 'video.generate', 5)], ['render', 'v']))
    await runFreeSteps('p1', 'wf1', ['render', 'v'])
    expect(enrichApi.runWorkflow).toHaveBeenCalledWith('p1', 'wf1', { targets: ['render'] })
    vi.mocked(enrichApi.runWorkflow).mockClear()
    vi.mocked(enrichApi.getPlan).mockResolvedValue(plan([spend('v', 'video.generate', 5)], ['v']))
    expect(await runFreeSteps('p1', 'wf1', ['v'])).toBeNull()
    expect(enrichApi.runWorkflow).not.toHaveBeenCalled()
  })
})
