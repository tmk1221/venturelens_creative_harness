import dagre from 'dagre'
import type { Edge as RFEdge, Node as RFNode } from '@xyflow/react'
import type { Workflow } from './types'

/** Pure layout/formatting helpers for `GraphPanel`, split out to keep that file under the
 * project's ~400-line budget -- nothing here touches React state or the network. */

export const NODE_W = 176
export const NODE_H = 88

/** Dagre auto-layout, only for nodes with no saved position yet (`savedLayout`, from
 * `Workflow.layout` -- see `patch /workflows/{id}/layout`) -- a node the user already
 * dragged keeps its spot instead of jumping back to the auto-layout position. */
export function layoutPositions<T extends RFNode>(rfNodes: T[], rfEdges: RFEdge[], savedLayout: Record<string, { x: number; y: number }>): T[] {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 28, ranksep: 70 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const n of rfNodes) g.setNode(n.id, { width: NODE_W, height: NODE_H })
  for (const e of rfEdges) g.setEdge(e.source, e.target)
  dagre.layout(g)
  return rfNodes.map((n) => {
    const saved = savedLayout[n.id]
    if (saved) return { ...n, position: saved }
    const pos = g.node(n.id)
    return { ...n, position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 } }
  })
}

/** A workflow's node+edge *id set*, sorted -- changes only on add/remove, not on a plain
 * status/artifact poll, so it gates when `GraphPanel` re-runs layout vs. just patches data. */
export function structureKey(workflow: Workflow | null): string {
  if (!workflow) return ''
  const n = workflow.nodes.map((x) => x.id).sort().join(',')
  const e = workflow.edges.map((x) => x.id).sort().join(',')
  return `${n}|${e}`
}

/** First line of whichever prompt-ish param a node type happens to carry, for the generic
 * node body's text preview (specialised node bodies in `./nodes/*` don't use this). */
export function firstPromptLine(typeId: string, params: Record<string, unknown> | undefined): string {
  const text = (params?.prompt_text ?? params?.subject_motion_hint ?? params?.instruction ?? params?.text) as string | undefined
  if (typeof text !== 'string' || !text.trim()) return ''
  void typeId
  return text.split('\n')[0]!.slice(0, 120)
}

export function costLabel(cost: Record<string, number> | null | undefined): string | null {
  if (!cost) return null
  const total = Object.values(cost).reduce((sum, v) => sum + v, 0)
  return total > 0 ? `${total.toFixed(2)} cr` : null
}
