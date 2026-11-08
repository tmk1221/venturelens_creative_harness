import { memo, type ReactNode } from 'react'
import { Handle, Position } from '@xyflow/react'
import { CHARACTER_PATH_PREFIX, handleColor, humanNodeName, typeIcon, type HandleSpec } from './graphMeta'
import { BriefNode, CharacterNode, ModelPicker, OverlayPlaceNode, ProvidedClipNode, StudioButton } from './nodes'
import type { CastEntry, NodeRegistry, ProvidedClip } from './types'
import type { OverlayDepth, OverlayPosition } from './nodes/overlayPositions'

export interface GraphNodeData {
  nodeId: string
  typeId: string
  state: string
  stateLabel: string
  /** T29: every named input/output, for one `<Handle>` each (drag-to-connect targets a
   * specific input, not just "the node") -- replaces T28's single generic handle per side. */
  inputs: HandleSpec[]
  outputs: HandleSpec[]
  inCategory: string
  outCategory: string
  thumbUrls: { url: string; selected: boolean }[]
  promptLine: string
  costLabel: string | null
  onClick: () => void
  // T30d: this node's own raw params + the shared registry/catalogues, plus callbacks bound
  // to this node's id -- everything the specialised in-node bodies (`./nodes/*`) need.
  params: Record<string, unknown>
  registry: NodeRegistry | null
  castList: CastEntry[]
  providedClips: ProvidedClip[]
  onPatchParams: (params: Record<string, unknown>) => void
  onRunNode: () => Promise<unknown>
  onCreateCastEntry: (name: string) => Promise<CastEntry>
  [key: string]: unknown
}

/** T30d: node types with a fully specialised body (replaces the generic thumbs/prompt-line
 * body below) -- `brief.write`'s editable instruction + Generate, `provided.clip`'s catalogue
 * picker + trim, and a `source.file` node marked as a character reference (see
 * `graphMeta.ts`'s `PALETTE` docstring on `CHARACTER_PATH_PREFIX`). `overlay.place` also gets
 * one (depth/position selects) even though it has no thumbs/prompt to replace. */
function specialBody(data: GraphNodeData): ReactNode | null {
  if (data.typeId === 'brief.write') {
    return (
      <BriefNode
        instruction={String(data.params.instruction ?? '')}
        state={data.state}
        onPatchParams={data.onPatchParams}
        onRunNode={data.onRunNode}
      />
    )
  }
  if (data.typeId === 'provided.clip') {
    return (
      <ProvidedClipNode
        path={String(data.params.path ?? '')}
        inSeconds={Number(data.params.in_seconds ?? 0)}
        outSeconds={data.params.out_seconds == null ? null : Number(data.params.out_seconds)}
        clips={data.providedClips}
        onPatchParams={data.onPatchParams}
      />
    )
  }
  if (data.typeId === 'source.file' && String(data.params.path ?? '').startsWith(CHARACTER_PATH_PREFIX)) {
    return (
      <CharacterNode
        path={String(data.params.path ?? '')}
        castList={data.castList}
        onPatchParams={data.onPatchParams}
        onCreateCastEntry={data.onCreateCastEntry}
      />
    )
  }
  if (data.typeId === 'overlay.place') {
    return (
      <OverlayPlaceNode
        depth={(data.params.depth as OverlayDepth) ?? 'in_front'}
        position={(data.params.position as OverlayPosition) ?? 'right'}
        onPatchParams={data.onPatchParams}
      />
    )
  }
  return null
}

/** Evenly-spaced vertical offsets for `n` stacked handles on one side of a card, e.g. 2
 * handles land at 33%/67%, never flush against the rounded corners. */
function handleOffsets(n: number): string[] {
  if (n <= 1) return ['50%']
  return Array.from({ length: n }, (_, i) => `${((i + 1) / (n + 1)) * 100}%`)
}

const STATE_DOT: Record<string, string> = {
  done: 'var(--ok, #5fb07a)',
  needs_approval: 'var(--accent, #4d9be6)',
  needs_pick: 'var(--accent, #4d9be6)',
  ready: 'var(--gate, #d3a350)',
  stale: 'var(--gate, #d3a350)',
  failed: 'var(--bad, #d4685c)',
  blocked: '#4a4f5a',
  unresolved: '#4a4f5a',
}

/** T28 node card: a dark card matching `.visual-rail-card` (see legacy-look.css), a header
 * with a human name + small type icon (no raw ids), a body showing the thing -- thumbnails
 * for image/video nodes, the first prompt line for text nodes -- and a plain-word state pill.
 * Memoized so a poll-driven data update to *other* nodes never re-renders this one. */
function GraphNodeImpl({ data }: { data: GraphNodeData }) {
  const name = humanNodeName(data.typeId)
  const dot = STATE_DOT[data.state] ?? '#4a4f5a'
  const inOffsets = handleOffsets(data.inputs.length)
  const outOffsets = handleOffsets(data.outputs.length)
  const special = specialBody(data)
  const isSpendingModel = data.typeId === 'still.generate' || data.typeId === 'endframe.generate' || data.typeId === 'video.generate'
  return (
    <div
      className="graph-node"
      onClick={data.onClick}
      data-testid="graph-node"
      data-node-state={data.state}
      title={data.nodeId}
    >
      {data.inputs.map((inp, i) => (
        <Handle
          key={inp.name}
          id={inp.name}
          type="target"
          position={Position.Left}
          style={{ background: handleColor(inp.type), top: inOffsets[i] }}
          title={`${inp.name} (${inp.type})`}
        />
      ))}
      <div className="graph-node-head">
        <span className="graph-node-icon" aria-hidden="true">{typeIcon(data.outCategory)}</span>
        <span className="graph-node-name">{name}</span>
        {data.costLabel && <span className="graph-node-cost">{data.costLabel}</span>}
      </div>
      {/* T30d: the model picker sits at the TOP of the node (spec: "a select at the top of
          the node") -- above the thumb/prompt body, not inside it. */}
      {isSpendingModel && (
        <ModelPicker
          typeId={data.typeId}
          model={String(data.params.model ?? '')}
          registry={data.registry}
          onChange={(modelId) => data.onPatchParams({ ...data.params, model: modelId })}
          compact
        />
      )}
      <div className="graph-node-body">
        {special ? (
          special
        ) : data.thumbUrls.length > 0 ? (
          <div className="graph-node-thumbs">
            {data.thumbUrls.slice(0, 3).map((t, i) =>
              data.outCategory === 'video' ? (
                <video key={i} src={t.url} className={t.selected ? 'graph-thumb is-selected' : 'graph-thumb'} muted playsInline />
              ) : (
                <img key={i} src={t.url} alt="" className={t.selected ? 'graph-thumb is-selected' : 'graph-thumb'} />
              ),
            )}
          </div>
        ) : data.promptLine ? (
          <div className="graph-node-prompt">{data.promptLine}</div>
        ) : (
          <div className="graph-node-empty" />
        )}
      </div>
      {data.typeId === 'animation.design' && <StudioButton nodeId={data.nodeId} />}
      <div className="graph-node-pill">
        <span className="graph-node-dot" style={{ background: dot }} />
        {data.stateLabel}
      </div>
      {/* Full node id, for the e2e locator and for anyone inspecting the DOM -- not shown
          visually (see the task spec: "No raw ids anywhere (tooltip only)"); the `title`
          attribute above already covers the hover tooltip. */}
      <span className="graph-node-id-sr">{data.nodeId}</span>
      {data.outputs.map((out, i) => (
        <Handle
          key={out.name}
          id={out.name}
          type="source"
          position={Position.Right}
          style={{ background: handleColor(out.type), top: outOffsets[i] }}
          title={`${out.name} (${out.type})`}
        />
      ))}
    </div>
  )
}

export const GraphNode = memo(GraphNodeImpl)
