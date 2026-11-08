import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import * as enrichApi from './api'
import { EnrichApiError } from './api'
import { useJobsStore } from '../store/jobsStore'
import { useSpendConfirmStore } from '../store/spendConfirmStore'
import { runFreeSteps, runWithSpendConfirm } from './spend'
import type { NodeStatus, Plan, Workflow } from './types'

interface WorkflowData {
  workflow: Workflow | null
  nodes: NodeStatus[]
  loading: boolean
  error: string | null
}

/** T30e: a brand-new span can have more than one mounted consumer racing to instantiate its
 * workflow at once (a card's own on-mount call, plus the workspace-level graph panel's own
 * instance once its graph is opened before the card has finished planning) -- each an
 * independent `useWorkflow` hook, since the workspace panel deliberately does not share the
 * card's instance (`graphPanelStore`'s docstring: keeping the open graph structurally
 * independent of any one card). `ensureSpanWorkflow`'s write is optimistic-concurrency
 * guarded (`expected_rev`), so the loser of that race gets a 409 -- but by then the winner has
 * already recorded the span's `workflow_id`, so recover by refetching the cut instead of
 * treating it as a fatal error. */
async function recoverWorkflowId(pid: string, cutId: string, spanId: string): Promise<string | null> {
  const { data } = await api.GET('/api/projects/{pid}/cuts/{cut_id}', { params: { path: { pid, cut_id: cutId } } })
  return data?.cut.spans.find((s) => s.id === spanId)?.workflow_id ?? null
}

// Polling is only the fallback net: the project's SSE stream (`useJobsStore`, connected at
// the shell level) pushes a job event per state change, and the effect below refreshes
// immediately whenever one lands for this workflow. The slow interval here just covers gaps
// (missed/late events, first paint) so a card never gets stuck if a browser event is lost.
const POLL_MS = 4000
const ACTIVE_POLL_MS = 1500

/** Owns one span's workflow: instantiates it on first mount (idempotent server-side), then
 * keeps `/nodes` (state badges, variant grids, clip player) live by refreshing on every
 * matching SSE job event from the project stream, with a slow poll as a safety net. */
export function useWorkflow(pid: string | null, cutId: string | null, spanId: string, hasRecipe: boolean) {
  const [data, setData] = useState<WorkflowData>({ workflow: null, nodes: [], loading: false, error: null })
  const workflowIdRef = useRef<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  // Once the user has run something, keep nudging FREE steps forward (e.g. a render that an
  // approval just unblocked -- an approval is not a job, so nothing server-side continues
  // from it). T31: only free steps (`spend.runFreeSteps`), never a spend: spending chains
  // continue server-side under the click's own authorisation (`queue.enqueue` stamps it on
  // free jobs too), and a spending node that's merely `ready` waits for a confirmed click.
  // `enqueue`'s `_existing_live_job` de-dupe makes a repeat call a safe no-op.
  const hasRunRef = useRef(false)
  const autoRunInFlightRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const refresh = useCallback(async () => {
    if (!pid || !workflowIdRef.current) return
    try {
      const [{ workflow }, nodes] = await Promise.all([
        enrichApi.getWorkflow(pid, workflowIdRef.current),
        enrichApi.getNodeStatuses(pid, workflowIdRef.current),
      ])
      if (!mountedRef.current) return
      setData({ workflow, nodes, loading: false, error: null })
      const readyIds = nodes.filter((n) => n.state === 'ready').map((n) => n.id)
      if (hasRunRef.current && readyIds.length > 0 && !autoRunInFlightRef.current) {
        autoRunInFlightRef.current = true
        runFreeSteps(pid, workflowIdRef.current!, readyIds)
          .catch(() => undefined)
          .finally(() => {
            autoRunInFlightRef.current = false
          })
      }
      const active = readyIds.length > 0 || autoRunInFlightRef.current
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(refresh, active ? ACTIVE_POLL_MS : POLL_MS)
    } catch (err) {
      if (!mountedRef.current) return
      setData((d) => ({ ...d, loading: false, error: err instanceof Error ? err.message : 'load failed' }))
    }
  }, [pid])

  const start = useCallback(async () => {
    if (!pid || !cutId || !hasRecipe) return
    setData((d) => ({ ...d, loading: true, error: null }))
    try {
      const ref = await enrichApi.ensureSpanWorkflow(pid, cutId, spanId)
      workflowIdRef.current = ref.workflow_id
      await refresh()
    } catch (err) {
      if (err instanceof EnrichApiError && err.status === 409) {
        const recovered = await recoverWorkflowId(pid, cutId, spanId)
        if (recovered) {
          workflowIdRef.current = recovered
          await refresh()
          return
        }
      }
      if (!mountedRef.current) return
      setData((d) => ({ ...d, loading: false, error: err instanceof Error ? err.message : 'could not plan this beat' }))
    }
  }, [pid, cutId, spanId, hasRecipe, refresh])

  useEffect(() => {
    start()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, cutId, spanId, hasRecipe])

  // SSE-driven refresh: the project stream carries every job's events (queued/progress/
  // result/failed); any event naming this workflow means a node's state may have just
  // changed, so refresh right away instead of waiting for the next poll tick.
  const lastJobEvent = useJobsStore((s) => {
    let latest: { workflow_id: string | null; seq: number } | null = null
    for (const job of s.jobsById.values()) {
      if (job.workflow_id === workflowIdRef.current && (!latest || job.seq > latest.seq)) latest = job
    }
    return latest?.seq ?? null
  })
  useEffect(() => {
    if (lastJobEvent === null || !workflowIdRef.current) return
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastJobEvent])

  const withRefresh = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T> => {
      const out = await fn()
      await refresh()
      return out
    },
    [refresh],
  )

  return {
    ...data,
    workflowId: workflowIdRef.current,
    refresh,
    // T29: reachable regardless of whether instantiation ever succeeded -- a card whose
    // `span_workflow` call failed (`wf.error` set, `workflowIdRef.current` never set, per
    // that route's own early-HTTPException-before-persist behaviour) can retry the same
    // idempotent call without a remount.
    retry: start,
    plan: useCallback(
      (targets?: string[], fromNode?: string): Promise<Plan> =>
        pid && workflowIdRef.current ? enrichApi.getPlan(pid, workflowIdRef.current, targets, fromNode) : Promise.reject(new Error('no workflow')),
      [pid],
    ),
    patchNode: useCallback(
      (nodeId: string, body: { params?: Record<string, unknown>; selected?: string }) =>
        pid && workflowIdRef.current ? withRefresh(() => enrichApi.patchNode(pid, workflowIdRef.current!, nodeId, body)) : Promise.reject(new Error('no workflow')),
      [pid, withRefresh],
    ),
    editEdges: useCallback(
      (edits: Parameters<typeof enrichApi.editEdges>[2]) =>
        pid && workflowIdRef.current ? withRefresh(() => enrichApi.editEdges(pid, workflowIdRef.current!, edits)) : Promise.reject(new Error('no workflow')),
      [pid, withRefresh],
    ),
    addNode: useCallback(
      (body: Parameters<typeof enrichApi.addNode>[2]) =>
        pid && workflowIdRef.current ? withRefresh(() => enrichApi.addNode(pid, workflowIdRef.current!, body)) : Promise.reject(new Error('no workflow')),
      [pid, withRefresh],
    ),
    deleteNode: useCallback(
      (nodeId: string) =>
        pid && workflowIdRef.current ? withRefresh(() => enrichApi.deleteNode(pid, workflowIdRef.current!, nodeId)) : Promise.reject(new Error('no workflow')),
      [pid, withRefresh],
    ),
    // T31: every run is plan -> (if it spends) the shell's "≈ X credits" confirm -> one
    // budget for exactly this click -> run. Resolves `{ cancelled: true }` on Cancel.
    run: useCallback(
      (opts: { targets?: string[]; fromNode?: string } = {}) => {
        hasRunRef.current = true
        return pid && workflowIdRef.current
          ? withRefresh(() => runWithSpendConfirm(pid, workflowIdRef.current!, opts, useSpendConfirmStore.getState().request))
          : Promise.reject(new Error('no workflow'))
      },
      [pid, withRefresh],
    ),
    approve: useCallback(
      (contentHash: string) => (pid ? withRefresh(() => enrichApi.approveContentHash(pid, contentHash)) : Promise.reject(new Error('no project'))),
      [pid, withRefresh],
    ),
    getArtifact: useCallback(
      (nodeId: string) => (pid && workflowIdRef.current ? enrichApi.getNodeArtifact(pid, workflowIdRef.current, nodeId) : Promise.reject(new Error('no workflow'))),
      [pid],
    ),
  }
}
