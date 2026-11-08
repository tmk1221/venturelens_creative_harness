import { useEffect, useMemo, useState } from 'react'
import { useCutStore } from '../store/cutStore'
import { useGraphPanelStore } from '../store/graphPanelStore'
import type { SpanCard } from '../edit/rawTranscript'
import { AlphaClipPlayer } from './card/AlphaClipPlayer'
import { ApproveGate } from './card/ApproveGate'
import { headerNode, videoFrameLabel } from './card/cardSummary'
import { ClipPlayer } from './card/ClipPlayer'
import { CompositePreview } from './card/CompositePreview'
import { EndFrame } from './card/EndFrame'
import { MoreVariantsButton } from './card/MoreVariantsButton'
import { StateBadge } from './card/StateBadge'
import { StillGrid } from './card/StillGrid'
import { EnrichApiError } from './api'
import type { NodeArtifact, NodeStatus } from './types'
import { useGraphArtifacts } from './useGraphArtifacts'
import { useWorkflow } from './useWorkflow'

// Two Span.kind naming generations both carry a recipe: T24's VISUALS picker ids
// ("video"/"anim", still written by the enrich e2e fixture's raw `add_span`) and T30a's
// PictureKind values ("live_action"/"motion_graphic", written by `add_beat_spans` -- the
// only op the dialog/suggester-accept paths use now). See `post_api/routes/enrich.py`'s
// `KIND_TO_RECIPE`, which recognizes the same pairs.
const RECIPE_KINDS = new Set(['video', 'live_action', 'anim', 'motion_graphic', 'overlay', 'provided'])

// `GET .../nodes` (`NodeStatus`, what `wf.nodes` carries) is state/hash/outputs only -- no
// `params` (see `routes/workflows.py::workflow_nodes`). A node's params live on
// `wf.workflow.nodes` (`GET .../workflows/{id}`) instead.
function paramsOf(wf: ReturnType<typeof useWorkflow>, nodeId: string | undefined): Record<string, unknown> | undefined {
  return nodeId ? wf.workflow?.nodes.find((n) => n.id === nodeId)?.params : undefined
}

function spentCost(nodes: NodeStatus[], artifacts: Map<string, NodeArtifact>): number {
  let total = 0
  for (const n of nodes) {
    const a = artifacts.get(n.id)
    if (a?.cost) total += Object.values(a.cost).reduce((sum, v) => sum + v, 0)
  }
  return total
}

/** T26/T30c card view: mounted inside `.visual-rail-card` (VisualsRail.tsx) for any span
 * whose kind carries a generative recipe. Drives one workflow end to end, branching per
 * recipe shape (live_action's still->pick->motion->[endframe]->video->approve, motion_
 * graphic's two-gate brief->design->draft->approve->render->approve, overlay's provided->
 * [measure->cutout]->place->approve with a composite preview when behind, provided's plain
 * clip->approve) plus a Graph view toggle -- the per-node-type pieces live under `card/` to
 * keep this file under the project's ~400-line budget. */
export function CardBody({
  card, onHasOutput,
}: {
  card: SpanCard
  onHasOutput?: (hasOutput: boolean) => void
}) {
  const pid = useCutStore((s) => s.pid)
  const cutId = useCutStore((s) => s.cutId)
  const span = card.span
  const hasRecipe = RECIPE_KINDS.has(span.kind)
  const wf = useWorkflow(pid, cutId, span.id ?? '', hasRecipe)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  // T30e: which span's graph is open is workspace-level state now (`graphPanelStore`'s
  // docstring) -- this card only reads whether IT is the open one, to show "Hide graph" and
  // to ask for its own graph the same way a Decisions row or the dialog's "Open in graph"
  // exit does. The panel itself renders once, outside this card, in `WorkspaceGraphPanel`.
  const openSpanId = useGraphPanelStore((s) => s.openSpanId)
  const openGraph = useGraphPanelStore((s) => s.openGraph)
  const closeGraph = useGraphPanelStore((s) => s.closeGraph)
  const showGraph = openSpanId === span.id
  const artifacts = useGraphArtifacts(pid ?? '', wf.workflowId, wf.nodes)

  useEffect(() => {
    onHasOutput?.(wf.nodes.some((n) => n.state === 'done' || n.state === 'needs_approval' || n.state === 'stale'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wf.nodes.map((n) => `${n.id}:${n.state}`).join(',')])

  const nodesById = useMemo(() => new Map(wf.nodes.map((n) => [n.id, n])), [wf.nodes])
  const bid = span.id ?? ''

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true)
    try {
      await fn()
    } catch (err) {
      window.alert(err instanceof EnrichApiError ? err.message : 'That failed. Try again.')
    } finally {
      setBusy(false)
    }
  }

  if (!hasRecipe) return null
  if (wf.error) {
    return (
      <div className="mt-2 text-xs space-y-1">
        <p className="text-red-600">Couldn't plan this beat: {wf.error}</p>
        <button type="button" className="underline" disabled={busy} onClick={() => void withBusy(wf.retry)}>Retry plan</button>
      </div>
    )
  }
  if (wf.loading && !wf.workflowId) return <p className="mt-2 text-xs text-neutral-500">Planning…</p>
  if (!wf.workflowId) return null

  return (
    <div className="mt-2 border-t border-neutral-200 dark:border-neutral-800 pt-2 text-xs space-y-2" data-testid="enrich-card-body">
      <CardHeader
        wf={wf} nodesById={nodesById} bid={bid} artifacts={artifacts} showGraph={showGraph}
        onToggleGraph={() => (showGraph ? closeGraph() : openGraph(span.id ?? ''))}
      />

      {(span.kind === 'video' || span.kind === 'live_action') && (
        <LiveActionBody bid={bid} pid={pid} cutId={cutId} nodesById={nodesById} artifacts={artifacts} wf={wf} busy={busy} withBusy={withBusy} note={note} setNote={setNote} />
      )}
      {(span.kind === 'anim' || span.kind === 'motion_graphic') && <MotionGraphicBody bid={bid} nodesById={nodesById} artifacts={artifacts} wf={wf} busy={busy} withBusy={withBusy} />}
      {span.kind === 'overlay' && (
        <OverlayBody bid={bid} behind={span.overlay_depth === 'behind'} nodesById={nodesById} artifacts={artifacts} wf={wf} busy={busy} withBusy={withBusy} />
      )}
      {span.kind === 'provided' && <ProvidedBody bid={bid} nodesById={nodesById} artifacts={artifacts} wf={wf} busy={busy} withBusy={withBusy} />}
    </div>
  )
}

function CardHeader({
  wf, nodesById, bid, artifacts, showGraph, onToggleGraph,
}: {
  wf: ReturnType<typeof useWorkflow>
  nodesById: Map<string, NodeStatus>
  bid: string
  artifacts: Map<string, NodeArtifact>
  showGraph: boolean
  onToggleGraph: () => void
}) {
  const overallNode = headerNode(wf.nodes, nodesById, bid)
  const overallState = overallNode?.state ?? 'unresolved'
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-1 flex-wrap">
        <StateBadge typeId={overallNode?.type_id ?? ''} state={overallState} failCause={overallNode?.fail_cause} />
        {spentCost(wf.nodes, artifacts) > 0 && <span className="text-neutral-500">spent {spentCost(wf.nodes, artifacts).toFixed(2)} cr</span>}
      </div>
      <button type="button" data-testid="enrich-graph-toggle" className="underline text-neutral-500" onClick={onToggleGraph}>
        {showGraph ? 'Hide graph' : 'Graph view'}
      </button>
    </div>
  )
}

function LiveActionBody({
  bid, pid, cutId, nodesById, artifacts, wf, busy, withBusy, note, setNote,
}: {
  bid: string
  pid: string | null
  cutId: string | null
  nodesById: Map<string, NodeStatus>
  artifacts: Map<string, NodeArtifact>
  wf: ReturnType<typeof useWorkflow>
  busy: boolean
  withBusy: (fn: () => Promise<unknown>) => Promise<void>
  note: string
  setNote: (v: string) => void
}) {
  const stillNodes = wf.nodes.filter((n) => n.type_id === 'still.generate').sort((a, b) => a.id.localeCompare(b.id))
  const pickNode = nodesById.get(`${bid}-pick`)
  const motionNode = nodesById.get(`${bid}-motion`)
  const endframeNode = nodesById.get(`${bid}-endframe`)
  const videoNode = nodesById.get(`${bid}-video`)
  const verifyNode = nodesById.get(`${bid}-verify`)
  const approveNode = nodesById.get(`${bid}-approve`)
  const frame = videoFrameLabel(paramsOf(wf, videoNode?.id))

  async function onApprove() {
    if (!approveNode?.input_hash) return
    await withBusy(() => wf.approve(approveNode.input_hash!))
  }
  async function onRegenerate() {
    if (!note.trim()) {
      window.alert('Add a note describing what should change before regenerating.')
      return
    }
    await withBusy(async () => {
      await wf.run({ targets: stillNodes.map((n) => n.id) })
      setNote('')
    })
  }

  return (
    <>
      {stillNodes.length > 0 && (
        <BriefEditor nodeId={stillNodes[0]!.id} params={paramsOf(wf, stillNodes[0]!.id)} wf={wf} />
      )}
      <StillGrid stillNodes={stillNodes} pickNode={pickNode} videoNode={videoNode} artifacts={artifacts} wf={wf} workflow={wf.workflow} busy={busy} withBusy={withBusy} label={`Generate ${stillNodes.length} variants`} />
      {pickNode?.selected && pid && cutId && <MoreVariantsButton pid={pid} cutId={cutId} spanId={bid} busy={busy} onAdded={wf.refresh} />}
      {endframeNode && <EndFrame node={endframeNode} artifact={artifacts.get(endframeNode.id)} />}
      {motionNode && (
        <p className="text-neutral-500" data-testid="enrich-motion-prompt">
          Motion: {String((paramsOf(wf, motionNode.id) as { subject_motion_hint?: string } | undefined)?.subject_motion_hint ?? '')}
        </p>
      )}
      {frame && <p className="text-neutral-500" data-testid="enrich-video-frame">Video: {frame}</p>}
      {videoNode && (videoNode.state === 'done' || videoNode.state === 'needs_approval' || videoNode.state === 'stale') && (
        <ClipPlayer node={videoNode} artifacts={artifacts} />
      )}
      <ApproveGate approveNode={approveNode} readyNode={verifyNode} busy={busy} onApprove={onApprove} testId="enrich-approve" />
      {approveNode && (approveNode.state === 'done' || approveNode.state === 'stale') && (
        <div className="flex items-center gap-2">
          <input data-testid="enrich-regen-note" className="border rounded px-1 py-0.5 text-xs flex-1" placeholder="What should change?" value={note} onChange={(e) => setNote(e.target.value)} />
          <button type="button" data-testid="enrich-regenerate" disabled={busy} className="underline" onClick={() => void onRegenerate()}>Regenerate</button>
        </div>
      )}
    </>
  )
}

function MotionGraphicBody({
  bid, nodesById, artifacts, wf, busy, withBusy,
}: {
  bid: string
  nodesById: Map<string, NodeStatus>
  artifacts: Map<string, NodeArtifact>
  wf: ReturnType<typeof useWorkflow>
  busy: boolean
  withBusy: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const draftNode = nodesById.get(`${bid}-draft`)
  const approveDraftNode = nodesById.get(`${bid}-approve-draft`)
  const renderNode = nodesById.get(`${bid}-render`)
  const verifyNode = nodesById.get(`${bid}-verify`)
  const approveFinalNode = nodesById.get(`${bid}-approve-final`)

  async function approve(node: NodeStatus | undefined) {
    if (!node?.input_hash) return
    await withBusy(() => wf.approve(node.input_hash!))
  }

  return (
    <>
      <p className="text-neutral-500" data-testid="enrich-two-gate-label">Draft → approve → render</p>
      {draftNode && (draftNode.state === 'done' || draftNode.state === 'stale') && <ClipPlayer node={draftNode} artifacts={artifacts} testId="enrich-draft-clip" />}
      <ApproveGate approveNode={approveDraftNode} readyNode={draftNode} busy={busy} onApprove={() => approve(approveDraftNode)} testId="enrich-approve-draft" />
      {approveDraftNode?.state === 'done' && renderNode && (renderNode.state === 'done' || renderNode.state === 'stale') && (
        <ClipPlayer node={renderNode} artifacts={artifacts} testId="enrich-render-clip" />
      )}
      <ApproveGate approveNode={approveFinalNode} readyNode={verifyNode} busy={busy} onApprove={() => approve(approveFinalNode)} testId="enrich-approve-final" />
    </>
  )
}

function OverlayBody({
  bid, behind, nodesById, artifacts, wf, busy, withBusy,
}: {
  bid: string
  behind: boolean
  nodesById: Map<string, NodeStatus>
  artifacts: Map<string, NodeArtifact>
  wf: ReturnType<typeof useWorkflow>
  busy: boolean
  withBusy: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const placeNode = nodesById.get(`${bid}-place`)
  const verifyNode = nodesById.get(`${bid}-verify`)
  const approveNode = nodesById.get(`${bid}-approve`)

  async function onApprove() {
    if (!approveNode?.input_hash) return
    await withBusy(() => wf.approve(approveNode.input_hash!))
  }

  return (
    <>
      {placeNode && (
        <p className="text-neutral-500" data-testid="enrich-overlay-placement">
          {(() => {
            const p = paramsOf(wf, placeNode.id) as { depth?: string; position?: string } | undefined
            return `${p?.depth ?? ''} · ${p?.position ?? ''}`
          })()}
        </p>
      )}
      {behind && <CompositePreview overlayUrl={placeNode ? artifacts.get(placeNode.id)?.outputs[0]?.url as string | undefined : undefined} />}
      {placeNode && (placeNode.state === 'done' || placeNode.state === 'stale' || placeNode.state === 'needs_approval') && (
        <AlphaClipPlayer node={placeNode} artifacts={artifacts} />
      )}
      <ApproveGate approveNode={approveNode} readyNode={verifyNode} busy={busy} onApprove={onApprove} testId="enrich-approve" />
    </>
  )
}

function ProvidedBody({
  bid, nodesById, artifacts, wf, busy, withBusy,
}: {
  bid: string
  nodesById: Map<string, NodeStatus>
  artifacts: Map<string, NodeArtifact>
  wf: ReturnType<typeof useWorkflow>
  busy: boolean
  withBusy: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const clipNode = nodesById.get(`${bid}-provided`)
  const approveNode = nodesById.get(`${bid}-approve`)

  async function onApprove() {
    if (!approveNode?.input_hash) return
    await withBusy(() => wf.approve(approveNode.input_hash!))
  }

  return (
    <>
      {clipNode && (clipNode.state === 'done' || clipNode.state === 'stale' || clipNode.state === 'needs_approval') && (
        <ClipPlayer node={clipNode} artifacts={artifacts} />
      )}
      <ApproveGate approveNode={approveNode} readyNode={clipNode} busy={busy} onApprove={onApprove} testId="enrich-approve" />
    </>
  )
}

function BriefEditor({ nodeId, params, wf }: { nodeId: string; params: Record<string, unknown> | undefined; wf: ReturnType<typeof useWorkflow> }) {
  const initial = String(params?.prompt_text ?? '')
  const [value, setValue] = useState(initial)
  useEffect(() => setValue(initial), [initial])
  return (
    <div>
      <textarea
        data-testid="enrich-brief" className="w-full border rounded px-1 py-1 text-xs" rows={2} value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          if (value !== initial) wf.patchNode(nodeId, { params: { prompt_text: value } })
        }}
      />
    </div>
  )
}
