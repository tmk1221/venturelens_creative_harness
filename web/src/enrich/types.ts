import type { components } from '../api/schema'

/** `/workflows/{id}` returns an untyped dict server-side (post_core's `Workflow` isn't a
 * response_model), so these mirror `packages/post_core/post_core/graph/workflow.py`'s
 * `Node`/`Edge`/`Workflow` shapes by hand. */
export interface WFNode {
  id: string
  type_id: string
  params: Record<string, unknown>
  /** Only meaningful for `human.pick` nodes: the id of the chosen incoming edge, or null. */
  selected: string | null
}

export interface WFEdge {
  id: string
  from_node: string
  from_output: string
  to_node: string
  to_input: string
}

export interface Workflow {
  id: string
  schema_version: number
  recipe_id: string
  brand_kit_hash: string | null
  nodes: WFNode[]
  edges: WFEdge[]
  layout: Record<string, unknown>
}

export type WorkflowState =
  | 'unresolved' | 'blocked' | 'ready' | 'done' | 'stale' | 'needs_pick' | 'needs_approval' | 'failed'

/** One row of `GET /workflows/{id}/nodes` -- state + hash + (if built) manifest outputs. */
export interface NodeStatus {
  id: string
  type_id: string
  state: WorkflowState
  input_hash: string | null
  selected: string | null
  outputs: { role?: string; sha256?: string; [k: string]: unknown }[]
  /** T29: the one-sentence cause when `state === 'failed'` (`queue.artifacts.mark_failed`'s
   * `failed.json` summary), null otherwise. */
  fail_cause: string | null
}

export interface NodeArtifact {
  exists: boolean
  outputs: { role?: string; sha256?: string; url?: string; [k: string]: unknown }[]
  /** Manifest shape actually written by `recipes.workers._common.emit_artifact_ok`: one
   * entry per spend unit, e.g. `{"credits": 2.5}` -- not `{amount, unit, provider}`. */
  cost: Record<string, number> | null
  content_hash?: string
}

export type NodeRegistry = components['schemas']['NodeRegistryOut']
export type NodeTypeInfo = components['schemas']['NodeTypeOut']
export type ModelOption = components['schemas']['ModelOptionOut']
export type Plan = components['schemas']['PlanOut']['plan']

/** T31: one entry of a plan's `spends` (`post_core.graph.plan.NodeSpend`) -- every spending
 * node a run leads to without another human decision, with its own estimate (`amount`/`unit`
 * null when none could be made). `runnable: false` = reached later via `covers_downstream`. */
export interface PlanSpend {
  node_id: string
  type_id: string
  amount: number | null
  unit: string | null
  provider: string | null
  runnable: boolean
}

// T30d: cast registry entries (character node picker) and the provided-clip catalogue
// (provided.clip node picker) -- both served by `routes/enrich.py`.
export type CastEntry = components['schemas']['CastEntryOut']
export type ProvidedClip = components['schemas']['ProvidedClipOut']
