import { useCutStore } from '../store/cutStore'
import { useGraphPanelStore } from '../store/graphPanelStore'
import { GraphPanel } from './GraphPanel'
import { useWorkflow } from './useWorkflow'

/** T30e (owner click-through): the single workspace-level graph panel -- see
 * `graphPanelStore`'s docstring for why this exists instead of each card rendering its own.
 * Mounted once by `EditWorkspace`, outside `VisualsRail`'s per-card tree entirely, so the
 * open graph's lifetime is independent of any one card's own render lifecycle. Owns its own
 * `useWorkflow` instance for whichever span is currently open -- a card showing that same
 * span (if still mounted) keeps its own instance running too; both are idempotent
 * server-side and `useWorkflow` itself now recovers from the 409 that can cause when both
 * instantiate a brand-new span's workflow around the same time (see its own docstring). */
export function WorkspaceGraphPanel() {
  const pid = useCutStore((s) => s.pid)
  const cutId = useCutStore((s) => s.cutId)
  const openSpanId = useGraphPanelStore((s) => s.openSpanId)
  const focusNodeId = useGraphPanelStore((s) => s.focusNodeId)
  const closeGraph = useGraphPanelStore((s) => s.closeGraph)
  const wf = useWorkflow(pid, cutId, openSpanId ?? '', openSpanId !== null)

  if (!openSpanId || !pid || !wf.workflowId) return null

  return (
    <GraphPanel
      pid={pid} workflowId={wf.workflowId} nodes={wf.nodes} workflow={wf.workflow}
      onClose={closeGraph} onChanged={wf.refresh} editEdges={wf.editEdges}
      run={wf.run} addNode={wf.addNode} patchNode={wf.patchNode} deleteNode={wf.deleteNode}
      focusNodeId={focusNodeId}
    />
  )
}
