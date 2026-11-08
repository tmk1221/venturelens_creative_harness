import { api } from '../api/client'
import type { CastEntry, NodeArtifact, NodeStatus, Plan, ProvidedClip, Workflow } from './types'

/** Thin typed wrappers over the T26 backend (`routes/enrich.py` + `routes/workflows.py`'s
 * generic `/workflows/{id}/...` routes). Every call either returns data or throws
 * `EnrichApiError` with the server's `detail`/`error` message, so callers can show the
 * "one-sentence cause" the spec asks for on a failure. */
export class EnrichApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) {
    const detail = (result.error as { detail?: string; error?: string } | undefined) ?? {}
    throw new EnrichApiError(result.response.status, detail.detail ?? detail.error ?? `request failed (${result.response.status})`)
  }
  return result.data
}

export async function ensureSpanWorkflow(pid: string, cutId: string, spanId: string) {
  const res = await api.POST('/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow', {
    params: { path: { pid, cut_id: cutId, span_id: spanId } },
  })
  return unwrap(res)
}

export async function getWorkflow(pid: string, workflowId: string): Promise<{ revision: number; workflow: Workflow }> {
  const res = await api.GET('/api/projects/{pid}/workflows/{workflow_id}', {
    params: { path: { pid, workflow_id: workflowId } },
  })
  return unwrap(res as never) as { revision: number; workflow: Workflow }
}

export async function getNodeStatuses(pid: string, workflowId: string): Promise<NodeStatus[]> {
  const res = await api.GET('/api/projects/{pid}/workflows/{workflow_id}/nodes', {
    params: { path: { pid, workflow_id: workflowId } },
  })
  return (unwrap(res as never) as { nodes: NodeStatus[] }).nodes
}

export async function getNodeArtifact(pid: string, workflowId: string, nodeId: string): Promise<NodeArtifact> {
  const res = await api.GET('/api/projects/{pid}/workflows/{workflow_id}/nodes/{node_id}/artifact', {
    params: { path: { pid, workflow_id: workflowId, node_id: nodeId } },
  })
  return unwrap(res as never) as NodeArtifact
}

export async function getPlan(pid: string, workflowId: string, targets?: string[], fromNode?: string): Promise<Plan> {
  const res = await api.GET('/api/projects/{pid}/workflows/{workflow_id}/plan', {
    params: {
      path: { pid, workflow_id: workflowId },
      query: { targets: targets ? JSON.stringify(targets) : undefined, from: fromNode },
    },
  })
  return unwrap(res).plan as Plan
}

export async function patchNode(
  pid: string, workflowId: string, nodeId: string,
  body: { params?: Record<string, unknown>; selected?: string },
) {
  const res = await api.PATCH('/api/projects/{pid}/workflows/{workflow_id}/nodes/{node_id}', {
    params: { path: { pid, workflow_id: workflowId, node_id: nodeId } },
    body: { params: body.params ?? {}, selected: body.selected },
  })
  return unwrap(res)
}

export async function addNode(
  pid: string, workflowId: string, body: { id?: string; type_id: string; params?: Record<string, unknown> },
) {
  const res = await api.POST('/api/projects/{pid}/workflows/{workflow_id}/nodes', {
    params: { path: { pid, workflow_id: workflowId } },
    body: { id: body.id, type_id: body.type_id, params: body.params ?? {} },
  })
  return unwrap(res)
}

export async function deleteNode(pid: string, workflowId: string, nodeId: string) {
  const res = await api.DELETE('/api/projects/{pid}/workflows/{workflow_id}/nodes/{node_id}', {
    params: { path: { pid, workflow_id: workflowId, node_id: nodeId } },
  })
  return unwrap(res)
}

export async function editEdges(
  pid: string, workflowId: string,
  edits: { add?: { id?: string; from_node: string; from_output: string; to_node: string; to_input: string }[]; remove?: string[] },
) {
  const res = await api.POST('/api/projects/{pid}/workflows/{workflow_id}/edges', {
    params: { path: { pid, workflow_id: workflowId } },
    body: { add: edits.add ?? [], remove: edits.remove ?? [] },
  })
  return unwrap(res)
}

export async function patchLayout(pid: string, workflowId: string, positions: Record<string, { x: number; y: number }>) {
  const res = await api.PATCH('/api/projects/{pid}/workflows/{workflow_id}/layout', {
    params: { path: { pid, workflow_id: workflowId } },
    body: { positions },
  })
  return unwrap(res)
}

/** T31: a run never creates a budget. Spending runs go through `spend.ts`'s
 * `runWithSpendConfirm`, which creates one budget per confirmed click (cap = the shown
 * estimate) via `putBudget` and passes it here with the exact node ids shown; a run with no
 * `budget` can only enqueue free nodes (the server refuses any spend with a 402). */
export async function runWorkflow(
  pid: string, workflowId: string,
  opts: { targets?: string[]; fromNode?: string; budget?: string; nodeIds?: string[]; by?: string; coversDownstream?: boolean } = {},
) {
  const res = await api.POST('/api/projects/{pid}/workflows/{workflow_id}/run', {
    params: { path: { pid, workflow_id: workflowId } },
    body: {
      targets: opts.targets, from_node: opts.fromNode, budget: opts.budget, node_ids: opts.nodeIds,
      by: opts.by ?? 'web', covers_downstream: opts.coversDownstream ?? false,
    },
  })
  return unwrap(res)
}

export async function putBudget(pid: string, budgetId: string, cap: number, unit: string) {
  const res = await api.PUT('/api/projects/{pid}/budgets/{budget_id}', {
    params: { path: { pid, budget_id: budgetId } },
    body: { cap, unit },
  })
  return unwrap(res)
}

export async function approveContentHash(pid: string, contentHash: string, by = 'web') {
  const res = await api.POST('/api/projects/{pid}/approvals', {
    params: { path: { pid } },
    body: { content_hash: contentHash, by },
  })
  return unwrap(res)
}

export async function getNodeRegistry(pid: string) {
  const res = await api.GET('/api/projects/{pid}/node-registry', { params: { path: { pid } } })
  return unwrap(res)
}

/** T39: ask `higgsfield model list` again; the next `getNodeRegistry` lists the fresh set. */
export async function refreshModels(pid: string) {
  const res = await api.POST('/api/projects/{pid}/models/refresh', { params: { path: { pid } } })
  return unwrap(res)
}

/** T30c card action ("+3 more" on a `live_action` card's still grid). */
export async function moreVariants(pid: string, cutId: string, spanId: string, count = 3) {
  const res = await api.POST('/api/projects/{pid}/cuts/{cut_id}/spans/{span_id}/workflow/more-variants', {
    params: { path: { pid, cut_id: cutId, span_id: spanId } },
    body: { count },
  })
  return unwrap(res)
}

// T30d: cast registry (character node picker) and the provided-clip catalogue (provided.clip
// node picker) -- both fixture/fake-mode only, per the node-picker specs.
export async function getCastList(pid: string): Promise<CastEntry[]> {
  const res = await api.GET('/api/projects/{pid}/cast', { params: { path: { pid } } })
  return (unwrap(res as never) as { cast: CastEntry[] }).cast
}

export async function createCastEntry(pid: string, body: { name: string; kind?: string; description?: string }): Promise<CastEntry> {
  const res = await api.POST('/api/projects/{pid}/cast', {
    params: { path: { pid } },
    body: { name: body.name, kind: body.kind ?? 'character', description: body.description ?? '' },
  })
  return unwrap(res as never) as CastEntry
}

export async function getProvidedCatalogue(pid: string): Promise<ProvidedClip[]> {
  const res = await api.GET('/api/projects/{pid}/provided-catalogue', { params: { path: { pid } } })
  return (unwrap(res as never) as { clips: ProvidedClip[] }).clips
}
