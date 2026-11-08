import { useCallback } from 'react'
import type { Node as RFNode } from '@xyflow/react'
import * as enrichApi from './api'
import { EnrichApiError } from './api'
import { NODE_W } from './graphLayout'
import type { GraphNodeData } from './GraphNode'
import type { PaletteItem } from './graphMeta'
import type { NodeTypeInfo, WFNode } from './types'

/** T29/T30d node-mutation handlers (palette add, duplicate, delete, param save, edge
 * disconnect, run-from-here), split out of `GraphPanel` to keep that file under the
 * project's ~400-line budget -- these are one cohesive concern (every way this panel
 * mutates the workflow other than drag-to-connect, which stays in `GraphPanel` alongside
 * `isValidConnection`/`onConnect`'s own state). */
export function useGraphPanelActions({
  pid, workflowId, selected, rfNodes, selectedNode, addNode, deleteNode, patchNode, editEdges, run,
  onChanged, setSelected,
}: {
  pid: string
  workflowId: string
  selected: string | null
  rfNodes: RFNode<GraphNodeData>[]
  selectedNode: WFNode | null
  addNode: (body: { id?: string; type_id: string; params?: Record<string, unknown> }) => Promise<{ node_id: string }>
  deleteNode: (nodeId: string) => Promise<unknown>
  patchNode: (nodeId: string, body: { params?: Record<string, unknown>; selected?: string }) => Promise<unknown>
  editEdges: (edits: { add?: { id?: string; from_node: string; from_output: string; to_node: string; to_input: string }[]; remove?: string[] }) => Promise<unknown>
  run: (opts?: { targets?: string[]; fromNode?: string }) => Promise<unknown>
  onChanged: () => void
  setSelected: (nodeId: string | null) => void
}) {
  // T29 item 1: a fresh palette node lands unconnected, near the selected node if there is
  // one, else near the current graph's centroid (a small deterministic jitter per call so
  // repeated adds with nothing selected don't stack exactly on top of each other).
  const nextPosition = useCallback(
    (): { x: number; y: number } => {
      if (selected) {
        const sel = rfNodes.find((n) => n.id === selected)
        if (sel) return { x: sel.position.x + NODE_W + 60, y: sel.position.y }
      }
      if (rfNodes.length === 0) return { x: 80, y: 80 }
      const cx = rfNodes.reduce((s, n) => s + n.position.x, 0) / rfNodes.length
      const cy = rfNodes.reduce((s, n) => s + n.position.y, 0) / rfNodes.length
      const jitter = (rfNodes.length % 5) * 26
      return { x: cx + jitter, y: cy + jitter }
    },
    [selected, rfNodes],
  )

  // A node type with a *required* input (e.g. `video.generate`) can't actually be saved
  // unconnected -- `graph.workflow.validate` (a pre-existing, deliberately-enforced
  // invariant, not something T29 changes) refuses to save any workflow where a required
  // input has no incoming edge at all, add-time included. The palette still offers every
  // registry node type (per the spec), but an add that the server rejects on that ground
  // surfaces as a plain alert instead of an unhandled rejection -- the fix is to wire it
  // (e.g. by first adding an upstream source) rather than something this panel can paper
  // over generically.
  async function addPaletteNode(nodeType: NodeTypeInfo, item: PaletteItem, defaultParams: Record<string, unknown>) {
    try {
      const pos = nextPosition()
      const params = { ...defaultParams, ...item.paramOverrides }
      const { node_id } = await addNode({ type_id: nodeType.id, params })
      await enrichApi.patchLayout(pid, workflowId, { [node_id]: pos })
      onChanged()
      setSelected(node_id)
    } catch (err) {
      window.alert(err instanceof EnrichApiError ? err.message : `Could not add a ${item.label} node.`)
    }
  }

  async function duplicateSelectedNode() {
    if (!selectedNode) return
    try {
      const pos = nextPosition()
      const { node_id } = await addNode({ type_id: selectedNode.type_id, params: selectedNode.params })
      await enrichApi.patchLayout(pid, workflowId, { [node_id]: pos })
      onChanged()
      setSelected(node_id)
    } catch (err) {
      window.alert(err instanceof EnrichApiError ? err.message : 'Could not duplicate that node.')
    }
  }

  async function deleteSelectedNode() {
    if (!selected) return
    try {
      await deleteNode(selected)
      setSelected(null)
      onChanged()
    } catch (err) {
      window.alert(err instanceof EnrichApiError ? err.message : 'Could not delete that node.')
    }
  }

  async function saveParams(nodeId: string, params: Record<string, unknown>) {
    try {
      await patchNode(nodeId, { params })
      onChanged()
    } catch (err) {
      window.alert(err instanceof EnrichApiError ? err.message : 'Could not save those params.')
    }
  }

  async function disconnectEdge(edgeId: string) {
    await editEdges({ remove: [edgeId] })
    onChanged()
  }

  async function runFromHere() {
    if (!selected) return
    await run({ fromNode: selected })
    onChanged()
  }

  return { addPaletteNode, duplicateSelectedNode, deleteSelectedNode, saveParams, disconnectEdge, runFromHere }
}
