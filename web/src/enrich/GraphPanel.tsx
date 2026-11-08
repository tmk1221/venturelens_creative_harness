import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background, BackgroundVariant, Controls, ReactFlow, ReactFlowProvider, useEdgesState, useNodesState,
  type Connection, type Edge as RFEdge, type Node as RFNode, type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import './graph.css'
import * as enrichApi from './api'
import { EnrichApiError } from './api'
import type { CastEntry, NodeRegistry, NodeTypeInfo, ProvidedClip, Workflow } from './types'
import { GraphNode, type GraphNodeData } from './GraphNode'
import { GraphInspector } from './GraphInspector'
import { useGraphArtifacts } from './useGraphArtifacts'
import { costLabel, firstPromptLine, layoutPositions, structureKey } from './graphLayout'
import {
  PALETTE, type PaletteItem, defaultParamsFor, nodeInputs, nodeOutputs, stateText, typesCompatible,
} from './graphMeta'
import { useGraphPanelActions } from './useGraphPanelActions'

interface Props {
  pid: string
  workflowId: string
  nodes: import('./types').NodeStatus[]
  workflow: Workflow | null
  onClose: () => void
  onChanged: () => void
  editEdges: (edits: { add?: { id?: string; from_node: string; from_output: string; to_node: string; to_input: string }[]; remove?: string[] }) => Promise<unknown>
  run: (opts?: { targets?: string[]; fromNode?: string }) => Promise<unknown>
  addNode: (body: { id?: string; type_id: string; params?: Record<string, unknown> }) => Promise<{ node_id: string }>
  patchNode: (nodeId: string, body: { params?: Record<string, unknown>; selected?: string }) => Promise<unknown>
  deleteNode: (nodeId: string) => Promise<unknown>
  /** T30d: another beat's "Open in graph" (T30c) opens straight into this graph already
   * fit/selected on one node -- e.g. the brief node right after "Generate prompt" is wired
   * up card-side. Only affects the very first render after this id (or the panel) changes;
   * the user's own later selection/pan/zoom is never overridden. */
  focusNodeId?: string
}

const nodeTypes = { status: GraphNode }

/** T28/T29: graph view. `useNodesState`/`useEdgesState` own the live node/edge arrays;
 * dagre runs once per workflow *structure* (node+edge id set), never on a status poll -- a
 * status/artifact update patches `node.data` on the existing array in place, so a drag in
 * progress is never fighting a relayout. `GraphNode` is memoized so an update to one node's
 * data doesn't re-render every other node's DOM.
 *
 * T29 adds: a palette of every hand-addable node type (unconnected, positioned near the
 * selected node or the graph's centroid -- the user wires it by dragging between named
 * handles, `isValidConnection` below rejecting a type mismatch before it ever reaches the
 * server), and Delete/Duplicate from the inspector. */
export function GraphPanel({
  pid, workflowId, nodes, workflow, onClose, onChanged, editEdges, run, addNode, patchNode, deleteNode,
  focusNodeId,
}: Props) {
  const [selected, setSelected] = useState<string | null>(null)
  const [registry, setRegistry] = useState<NodeRegistry | null>(null)
  // T30d: cast + provided-clip catalogue, read once per panel open -- feed the `character`
  // and `provided.clip` in-node pickers (`nodes/CharacterNode.tsx`, `nodes/
  // ProvidedClipNode.tsx`). Neither changes mid-session from inside this panel (cast/
  // provided-catalogue authoring is out of scope here), so a plain fetch-on-mount is enough;
  // `refetchCast` below only exists because *this* panel's own "new character" flow can add
  // one (`routes/enrich.py`'s minimal `POST .../cast`).
  const [castList, setCastList] = useState<CastEntry[]>([])
  const [providedClips, setProvidedClips] = useState<ProvidedClip[]>([])
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<RFNode<GraphNodeData>>([])
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<RFEdge>([])
  const structureRef = useRef<string>('')
  const rfInstanceRef = useRef<ReactFlowInstance<RFNode<GraphNodeData>, RFEdge> | null>(null)
  const focusedRef = useRef<string | undefined>(undefined)

  useEffect(() => {
    enrichApi.getNodeRegistry(pid).then(setRegistry).catch(() => setRegistry(null))
  }, [pid])

  // T39: the model picker's refresh button -- re-list Higgsfield's models, then re-read the registry.
  const refreshModels = useCallback(async () => {
    await enrichApi.refreshModels(pid)
    setRegistry(await enrichApi.getNodeRegistry(pid))
  }, [pid])

  const refetchCast = useCallback(() => {
    enrichApi.getCastList(pid).then(setCastList).catch(() => undefined)
  }, [pid])

  useEffect(() => {
    refetchCast()
    enrichApi.getProvidedCatalogue(pid).then(setProvidedClips).catch(() => undefined)
  }, [pid, refetchCast])

  const statusById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const artifacts = useGraphArtifacts(pid, workflowId, nodes)

  // Which nodes feed a `human.pick` node's currently-selected edge -- used to highlight the
  // matching thumbnail among a still.generate node's variants.
  const selectedByPick = useMemo(() => {
    const set = new Set<string>()
    if (!workflow) return set
    for (const n of workflow.nodes) {
      if (!n.selected) continue
      const edge = workflow.edges.find((e) => e.id === n.selected)
      if (edge) set.add(edge.from_node)
    }
    return set
  }, [workflow])

  const buildData = useCallback(
    (nodeId: string, typeId: string, params: Record<string, unknown> | undefined): GraphNodeData => {
      const status = statusById.get(nodeId)
      const state = status?.state ?? 'unresolved'
      const art = artifacts.get(nodeId)
      const thumbUrls = (art?.outputs ?? [])
        .filter((o) => typeof o.url === 'string')
        .map((o) => ({ url: o.url as string, selected: selectedByPick.has(nodeId) }))
      const inputs = nodeInputs(typeId, registry)
      const outputs = nodeOutputs(typeId, params, registry)
      return {
        nodeId,
        typeId,
        state,
        stateLabel: stateText(typeId, state, status?.fail_cause),
        inputs,
        outputs,
        inCategory: inputs[0]?.type ?? 'any',
        outCategory: outputs[0]?.type ?? 'any',
        thumbUrls,
        promptLine: firstPromptLine(typeId, params),
        costLabel: costLabel(art?.cost),
        onClick: () => setSelected(nodeId),
        // T30d: everything the specialised in-node bodies (`nodes/*`) need -- kept on `data`
        // (not read from closures inside `GraphNode`) so a memoized node only re-renders when
        // its own inputs actually changed, same reasoning as every other field here.
        params: params ?? {},
        registry,
        castList,
        providedClips,
        onPatchParams: (p: Record<string, unknown>) => {
          patchNode(nodeId, { params: p }).catch((err) => window.alert(err instanceof EnrichApiError ? err.message : 'Could not save those params.'))
        },
        // T30d: returns the in-flight promise (not fire-and-forget) so `BriefNode`'s own
        // "Generate" button can track a local busy flag across the click -- `state` alone
        // can't: a node with no required inputs (`brief.write`) is already `ready` (T30's
        // "Generating…" label, `graphMeta.stateText`) before it has ever run even once, and
        // stays `ready` for the job's whole in-flight duration too (`compute_states` only
        // moves it to `done` once a manifest lands) -- reading `state === 'ready'` as "is
        // this run's own click still in flight" would leave the button permanently disabled.
        onRunNode: () => run({ targets: [nodeId] }).catch((err) => {
          window.alert(err instanceof EnrichApiError ? err.message : 'Could not run that node.')
        }),
        onCreateCastEntry: async (name: string) => {
          const entry = await enrichApi.createCastEntry(pid, { name })
          refetchCast()
          return entry
        },
      }
    },
    [statusById, artifacts, selectedByPick, registry, castList, providedClips, patchNode, run, pid, refetchCast],
  )

  // Structural rebuild: only when the node/edge *id set* changes (add/remove node or edge),
  // never on a plain status/artifact refresh.
  useEffect(() => {
    if (!workflow) {
      setRfNodes([])
      setRfEdges([])
      structureRef.current = ''
      return
    }
    const key = structureKey(workflow)
    if (key === structureRef.current) return
    structureRef.current = key
    const freshNodes: RFNode<GraphNodeData>[] = workflow.nodes.map((n) => ({
      id: n.id,
      type: 'status',
      position: { x: 0, y: 0 },
      data: buildData(n.id, n.type_id, n.params),
    }))
    const freshEdges: RFEdge[] = workflow.edges.map((e) => ({
      id: e.id, source: e.from_node, target: e.to_node,
      sourceHandle: e.from_output, targetHandle: e.to_input,
      label: `${e.from_output}→${e.to_input}`,
      animated: statusById.get(e.to_node)?.state === 'ready',
    }))
    const savedLayout = (workflow.layout ?? {}) as Record<string, { x: number; y: number }>
    setRfNodes(layoutPositions(freshNodes, freshEdges, savedLayout))
    setRfEdges(freshEdges)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflow])

  // Data-only refresh: same structure, new status/artifact/registry info -- update each
  // node's `data` (and edge `animated`) without touching anyone's `position`.
  useEffect(() => {
    if (!workflow || structureKey(workflow) !== structureRef.current) return
    setRfNodes((prev) => prev.map((n) => {
      const wn = workflow.nodes.find((x) => x.id === n.id)
      return wn ? { ...n, data: buildData(n.id, wn.type_id, wn.params) } : n
    }))
    setRfEdges((prev) => prev.map((e) => ({ ...e, animated: statusById.get(e.target)?.state === 'ready' })))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusById, artifacts, selectedByPick, registry, castList, providedClips])

  // Close/Escape returns to the card.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // T30d: `focusNodeId` -- fit/select that node once, the first time it (or the graph) is
  // ready, then leave the user's own pan/zoom/selection alone. Guarded by `focusedRef` so a
  // later status/artifact refresh (which doesn't change `focusNodeId`) never re-triggers it.
  useEffect(() => {
    if (!focusNodeId || focusedRef.current === focusNodeId) return
    const node = rfNodes.find((n) => n.id === focusNodeId)
    if (!node) return
    focusedRef.current = focusNodeId
    setSelected(focusNodeId)
    rfInstanceRef.current?.fitView({ nodes: [{ id: focusNodeId }], padding: 0.4, duration: 300 })
  }, [focusNodeId, rfNodes])

  const onNodeDragStop = useCallback(
    (_event: unknown, node: RFNode) => {
      enrichApi.patchLayout(pid, workflowId, { [node.id]: { x: node.position.x, y: node.position.y } }).catch(() => undefined)
    },
    [pid, workflowId],
  )

  const selectedNode = workflow?.nodes.find((n) => n.id === selected) ?? null
  const selectedStatus = selected ? statusById.get(selected) : undefined
  const selectedType = registry?.node_types.find((t) => t.id === selectedNode?.type_id)

  // T29/T30d: every way this panel mutates the workflow other than drag-to-connect (that
  // stays below, alongside `isValidConnection`/`onConnect`'s own state) -- split into its own
  // hook to keep this file under the project's ~400-line budget.
  const {
    addPaletteNode: addPaletteNodeRaw, duplicateSelectedNode, deleteSelectedNode, saveParams, disconnectEdge, runFromHere,
  } = useGraphPanelActions({
    pid, workflowId, selected, rfNodes, selectedNode, addNode, deleteNode, patchNode, editEdges, run, onChanged, setSelected,
  })
  const addPaletteNode = (nodeType: NodeTypeInfo, item: PaletteItem) => addPaletteNodeRaw(nodeType, item, defaultParamsFor(nodeType))

  // T29: drag-to-connect between named handles, type-checked client-side before the server
  // ever sees it (`graph.workflow.validate` still has the last word -- `onConnect` below
  // surfaces a rejection from *that* as an alert, e.g. "already wired"/"required" issues
  // this check doesn't know about).
  const isValidConnection = useCallback(
    (conn: RFEdge | Connection) => {
      if (!workflow || !registry) return false
      const sourceNode = workflow.nodes.find((n) => n.id === conn.source)
      const targetNode = workflow.nodes.find((n) => n.id === conn.target)
      if (!sourceNode || !targetNode || !conn.sourceHandle || !conn.targetHandle) return false
      const out = nodeOutputs(sourceNode.type_id, sourceNode.params, registry).find((o) => o.name === conn.sourceHandle)
      const inp = nodeInputs(targetNode.type_id, registry).find((i) => i.name === conn.targetHandle)
      if (!out || !inp) return false
      return typesCompatible(out.type, inp.type)
    },
    [workflow, registry],
  )

  const onConnect = useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target || !conn.sourceHandle || !conn.targetHandle || !workflow) return
      // Dragging a new edge onto a single-slot (`many: false`) input that's already wired
      // replaces the old edge instead of the server rejecting the drop with "does not
      // accept many" -- both the remove and the add go in the one `editEdges` call so the
      // graph is never briefly left with that required input unwired (which the server's
      // own `assert_valid` would refuse to save on its own).
      const targetNode = workflow.nodes.find((n) => n.id === conn.target)
      const inputSpec = targetNode && nodeInputs(targetNode.type_id, registry).find((i) => i.name === conn.targetHandle)
      const remove = inputSpec && !inputSpec.many
        ? workflow.edges.filter((e) => e.to_node === conn.target && e.to_input === conn.targetHandle).map((e) => e.id)
        : []
      editEdges({
        add: [{ from_node: conn.source, from_output: conn.sourceHandle, to_node: conn.target, to_input: conn.targetHandle }],
        remove,
      })
        .then(onChanged)
        .catch((err) => window.alert(err instanceof EnrichApiError ? err.message : 'Could not connect those nodes.'))
    },
    [editEdges, onChanged, workflow, registry],
  )

  // T27 item 5: a rail-width side panel was unusable -- full-screen overlay instead, palette
  // moved into a top bar, Close/Escape (above) returns to the card. `fitView` (ReactFlow prop
  // below) still fits the graph to the viewport on open. `deleteKeyCode={null}` disables
  // ReactFlow's own keyboard node/edge deletion, which only updates local state -- every
  // delete goes through the inspector's explicit button so it's never out of sync with the
  // server's workflow.
  return (
    <div className="fixed inset-0 z-50 graph-panel flex flex-col" data-testid="enrich-graph-panel">
      <div className="graph-topbar flex items-center gap-3 px-3 py-2 text-sm flex-wrap">
        <strong>Graph</strong>
        {registry && PALETTE.map((item) => {
          const nt = registry.node_types.find((t) => t.id === item.typeId)
          if (!nt) return null
          return (
            <button
              key={`${item.typeId}-${item.label}`}
              type="button"
              className="underline"
              data-testid={`graph-add-${item.testId ?? item.typeId.replace('.', '-')}`}
              onClick={() => addPaletteNode(nt, item)}
            >
              + {item.label}
            </button>
          )
        })}
        <div className="ml-auto" />
        <button type="button" className="underline" onClick={onClose} data-testid="enrich-graph-close">
          Close
        </button>
      </div>
      <div className="flex flex-1 min-h-0">
        <div style={{ flex: 1, position: 'relative' }}>
          <ReactFlowProvider>
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              isValidConnection={isValidConnection}
              deleteKeyCode={null}
              fitView
              fitViewOptions={{ padding: 0.2 }}
              minZoom={0.2}
              proOptions={{ hideAttribution: true }}
              onNodeDragStop={onNodeDragStop}
              onInit={(instance) => {
                rfInstanceRef.current = instance
              }}
            >
              <Background variant={BackgroundVariant.Dots} color="#2d323c" gap={18} size={1} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </ReactFlowProvider>
        </div>
        <GraphInspector
          selectedNode={selectedNode}
          selectedStatus={selectedStatus}
          selectedType={selectedType}
          workflow={workflow}
          registry={registry}
          artifacts={artifacts}
          onDisconnect={disconnectEdge}
          onRunFromHere={runFromHere}
          onSaveParams={saveParams}
          onDelete={deleteSelectedNode}
          onDuplicate={duplicateSelectedNode}
          onRefreshModels={refreshModels}
        />
        <div style={{ display: 'none' }}>{workflowId}</div>
      </div>
    </div>
  )
}
