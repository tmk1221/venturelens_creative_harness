import * as enrichApi from './api'
import { EnrichApiError } from './api'
import type { Plan, PlanSpend } from './types'

/** T31: no click spends without a shown estimate. Every run the web starts goes through
 * `runWithSpendConfirm`: plan first; if the plan leads to any spending node, show "N stills,
 * M videos ≈ X credits" and only on Confirm create ONE budget for exactly that click (id from
 * workflow + time, cap = the shown estimate, unit from the plan) and run with an
 * authorisation naming exactly those node ids. `covers_downstream` stays on so a chain
 * (pick -> video -> verify) continues server-side, but the core refuses anything past the
 * cap, so a chain can never spend more than the person saw. */

/** A plan that can't be shown honestly as one estimate. An `EnrichApiError` (status 0) so
 * every existing caller's alert shows its one-sentence message. */
export class SpendError extends EnrichApiError {
  constructor(message: string) {
    super(0, message)
  }
}

export interface SpendSummary {
  nodeIds: string[]
  amount: number
  unit: string
  /** "3 stills, 1 video" */
  label: string
  /** The confirm's question when "Generate <label>?" doesn't fit, e.g. T35's "Transcribe episode-37.mp4?". */
  title?: string
}

export type ConfirmSpend = (summary: SpendSummary) => Promise<boolean>

const NOUNS: Record<string, [string, string]> = {
  'still.generate': ['still', 'stills'],
  'endframe.generate': ['end frame', 'end frames'],
  'video.generate': ['video', 'videos'],
}

export function planSpends(plan: Plan): PlanSpend[] {
  return ((plan as { spends?: PlanSpend[] }).spends ?? [])
}

/** null when the plan spends nothing; throws `SpendError` (one sentence) when it can't be
 * shown honestly -- a node with no estimate, or estimates in more than one unit. */
export function summarizeSpend(plan: Plan): SpendSummary | null {
  const spends = planSpends(plan)
  if (spends.length === 0) return null
  const blind = spends.find((s) => s.amount == null || !s.unit)
  if (blind) throw new SpendError(`${blind.node_id} has no cost estimate, so it won't run: nothing spends blind.`)
  const units = [...new Set(spends.map((s) => s.unit as string))]
  if (units.length > 1) throw new SpendError(`This run mixes ${units.join(' and ')}; run those parts separately.`)
  const counts = new Map<string, number>()
  for (const s of spends) counts.set(s.type_id, (counts.get(s.type_id) ?? 0) + 1)
  const label = [...counts.entries()]
    .map(([typeId, n]) => {
      const [one, many] = NOUNS[typeId] ?? [typeId, typeId]
      return `${n} ${n === 1 ? one : many}`
    })
    .join(', ')
  return {
    nodeIds: spends.map((s) => s.node_id),
    amount: spends.reduce((sum, s) => sum + (s.amount as number), 0),
    unit: units[0]!,
    label,
  }
}

export function formatEstimate(summary: SpendSummary): string {
  return `${summary.label} ≈ ${summary.amount.toFixed(2)} ${summary.unit}`
}

export async function runWithSpendConfirm(
  pid: string, workflowId: string, opts: { targets?: string[]; fromNode?: string },
  confirm: ConfirmSpend, now: () => number = Date.now,
): Promise<{ cancelled: true } | Awaited<ReturnType<typeof enrichApi.runWorkflow>>> {
  const plan = await enrichApi.getPlan(pid, workflowId, opts.targets, opts.fromNode)
  const summary = summarizeSpend(plan)
  if (!summary) return enrichApi.runWorkflow(pid, workflowId, opts)
  if (!(await confirm(summary))) return { cancelled: true }
  const budgetId = `${workflowId}-${now()}`
  await enrichApi.putBudget(pid, budgetId, summary.amount, summary.unit)
  return enrichApi.runWorkflow(pid, workflowId, {
    ...opts, budget: budgetId, nodeIds: summary.nodeIds, coversDownstream: true,
  })
}

/** The card's auto-continue nudge (`useWorkflow.refresh`): run only the FREE ready steps
 * (e.g. a render unblocked by an approval). Never spends, so never needs a confirm; a
 * spending node that's ready waits for a click. */
export async function runFreeSteps(pid: string, workflowId: string, readyIds: string[]) {
  const plan = await enrichApi.getPlan(pid, workflowId, readyIds)
  const spending = new Set(planSpends(plan).map((s) => s.node_id))
  const free = ((plan as { runnable?: string[] }).runnable ?? []).filter((id) => readyIds.includes(id) && !spending.has(id))
  if (free.length === 0) return null
  return enrichApi.runWorkflow(pid, workflowId, { targets: free })
}
