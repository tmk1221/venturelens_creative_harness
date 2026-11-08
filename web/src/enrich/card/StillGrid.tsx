import type { NodeArtifact, NodeStatus, Workflow } from '../types'
import type { useWorkflow } from '../useWorkflow'

function edgeId(workflow: Workflow | null, fromNode: string, toNode: string | undefined): string {
  if (!workflow || !toNode) return ''
  return workflow.edges.find((e) => e.from_node === fromNode && e.to_node === toNode)?.id ?? ''
}

/** The Generate/variant-grid/Pick flow shared by a card's `still.generate`
 * group (live_action's main stills, or -- via `StillGrid` reused with a different node
 * list -- the "+3 more" batch, which shares the same `human.pick` node so a picked variant
 * from either batch highlights the same way). Split out of `CardBody.tsx` to keep that file
 * under the project's line budget. T31: Generate and Pick both go through `wf.run`, whose
 * shell-level confirm (`SpendConfirmDialog`) shows the estimate before anything spends. */
export function StillGrid({
  stillNodes, pickNode, videoNode, artifacts, wf, workflow, busy, withBusy, label,
}: {
  stillNodes: NodeStatus[]
  pickNode: NodeStatus | undefined
  videoNode: NodeStatus | undefined
  artifacts: Map<string, NodeArtifact>
  wf: ReturnType<typeof useWorkflow>
  workflow: Workflow | null
  busy: boolean
  withBusy: (fn: () => Promise<unknown>) => Promise<void>
  label: string
}) {
  async function onGenerateClick() {
    await withBusy(() => wf.run({ targets: stillNodes.map((n) => n.id) }))
  }

  async function onPick(nodeId: string) {
    if (!pickNode) return
    await withBusy(async () => {
      await wf.patchNode(pickNode.id, { selected: edgeId(workflow, nodeId, pickNode.id) })
      if (videoNode) await wf.run({ targets: [videoNode.id] })
    })
  }

  return (
    <div>
      {!stillNodes.some((n) => n.state === 'done') && !pickNode?.selected && (
        <div>
          <button type="button" data-testid="enrich-generate" disabled={busy} className="px-2 py-1 rounded bg-blue-600 text-white disabled:opacity-50" onClick={onGenerateClick}>
            {label}
          </button>
        </div>
      )}

      {stillNodes.some((n) => n.state === 'done') && (
        <div data-testid="enrich-variant-grid" className="grid grid-cols-3 gap-1">
          {stillNodes.map((n) => {
            const art = artifacts.get(n.id)
            const still = art?.outputs[0]
            const selected = pickNode?.selected === edgeId(workflow, n.id, pickNode?.id)
            return (
              <div key={n.id} className={`border rounded p-1 ${selected ? 'border-emerald-500' : 'border-neutral-300'}`} data-testid="enrich-variant">
                {still?.url ? <img src={still.url} alt="" className="w-full h-16 object-cover rounded" /> : <div className="w-full h-16 bg-neutral-100 rounded" />}
                <button type="button" data-testid="enrich-pick" className="mt-1 w-full text-[10px] underline" onClick={() => onPick(n.id)} disabled={selected}>
                  {selected ? 'Picked' : 'Pick'}
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
