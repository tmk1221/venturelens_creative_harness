import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as enrichApi from '../enrich/api'
import { runWithSpendConfirm } from '../enrich/spend'
import { useProvidersStore } from '../store/providersStore'
import { useSpendConfirmStore } from '../store/spendConfirmStore'
import { SpendConfirmDialog } from './SpendConfirmDialog'

/** T31 acceptance (mocked API): a Generate click's confirm shows the estimate, and Confirm
 * sends exactly one budget (cap = that estimate) and one run whose authorisation names
 * explicit node ids. Drives the real store + dialog + `runWithSpendConfirm` together. */
vi.mock('../enrich/api', () => ({
  EnrichApiError: class EnrichApiError extends Error {},
  getPlan: vi.fn(),
  putBudget: vi.fn().mockResolvedValue({ budget: {} }),
  runWorkflow: vi.fn().mockResolvedValue({ workflow_id: 'wf1', job_ids: ['j1'], plan: {} }),
}))

const PLAN = {
  runnable: ['b-still0', 'b-still1', 'b-still2'], needs_authorization: [], blocked_on_human: [], estimated_cost: [],
  spends: ['b-still0', 'b-still1', 'b-still2'].map((node_id) => ({
    node_id, type_id: 'still.generate', amount: 1.5, unit: 'credits', provider: 'higgsfield', runnable: true,
  })),
}

beforeEach(() => {
  useSpendConfirmStore.setState({ pending: null })
  useProvidersStore.setState({ mode: 'real' })
  vi.mocked(enrichApi.getPlan).mockResolvedValue(PLAN as never)
  vi.mocked(enrichApi.putBudget).mockClear()
  vi.mocked(enrichApi.runWorkflow).mockClear()
})

function startGenerate() {
  return runWithSpendConfirm('p1', 'wf1', { targets: PLAN.runnable }, useSpendConfirmStore.getState().request, () => 42)
}

describe('SpendConfirmDialog', () => {
  it('shows the estimate, then Confirm sends one budget + one authorisation with explicit node ids', async () => {
    render(<SpendConfirmDialog />)
    let done!: Promise<unknown>
    await act(async () => {
      done = startGenerate()
    })
    expect(await screen.findByTestId('spend-confirm-estimate')).toHaveTextContent('3 stills ≈ 4.50 credits')
    expect(screen.getByTestId('spend-confirm')).toHaveTextContent('own budget of exactly 4.50 credits')
    expect(enrichApi.putBudget).not.toHaveBeenCalled()

    await act(async () => {
      fireEvent.click(screen.getByTestId('spend-confirm-ok'))
      await done
    })
    expect(enrichApi.putBudget).toHaveBeenCalledTimes(1)
    expect(enrichApi.putBudget).toHaveBeenCalledWith('p1', 'wf1-42', 4.5, 'credits')
    expect(enrichApi.runWorkflow).toHaveBeenCalledTimes(1)
    expect(vi.mocked(enrichApi.runWorkflow).mock.calls[0]![2]).toMatchObject({
      budget: 'wf1-42', nodeIds: ['b-still0', 'b-still1', 'b-still2'], coversDownstream: true,
    })
    expect(screen.queryByTestId('spend-confirm')).toBeNull()
  })

  it('Cancel closes the dialog and sends nothing', async () => {
    render(<SpendConfirmDialog />)
    let done!: Promise<unknown>
    await act(async () => {
      done = startGenerate()
    })
    await screen.findByTestId('spend-confirm')
    await act(async () => {
      fireEvent.click(screen.getByTestId('spend-confirm-cancel'))
      await done
    })
    expect(await done).toEqual({ cancelled: true })
    expect(enrichApi.putBudget).not.toHaveBeenCalled()
    expect(enrichApi.runWorkflow).not.toHaveBeenCalled()
  })

  it('says nothing is spent in fake mode', async () => {
    useProvidersStore.setState({ mode: 'fake' })
    render(<SpendConfirmDialog />)
    await act(async () => {
      void startGenerate()
    })
    expect(await screen.findByTestId('spend-confirm')).toHaveTextContent('nothing is actually spent')
  })
})
