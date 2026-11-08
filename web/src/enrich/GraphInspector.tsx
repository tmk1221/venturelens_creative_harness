import { useEffect, useState } from 'react'
import { MODEL_KIND, humanNodeName, stateText } from './graphMeta'
import { ModelPicker } from './nodes/ModelPicker'
import type { NodeArtifact, NodeRegistry, NodeStatus, NodeTypeInfo, Workflow, WFNode } from './types'

interface Props {
  selectedNode: WFNode | null
  selectedStatus: NodeStatus | undefined
  selectedType: NodeTypeInfo | undefined
  workflow: Workflow | null
  registry: NodeRegistry | null
  artifacts: Map<string, NodeArtifact>
  onDisconnect: (edgeId: string) => void
  onRunFromHere: () => void
  onSaveParams: (nodeId: string, params: Record<string, unknown>) => Promise<unknown>
  onDelete: () => void
  onDuplicate: () => void
  /** T39: re-read `higgsfield model list` (the model picker's refresh button). */
  onRefreshModels?: () => Promise<void>
}

type JSONSchemaProp = { type?: string; title?: string; enum?: string[]; anyOf?: { type?: string }[] }
type JSONSchema = { properties?: Record<string, JSONSchemaProp>; required?: string[] }

function widgetFor(name: string, prop: JSONSchemaProp): 'select' | 'number' | 'boolean' | 'image' | 'textarea' | 'text' {
  if (prop.enum) return 'select'
  const jsonType = prop.type ?? prop.anyOf?.find((s) => s.type && s.type !== 'null')?.type
  if (jsonType === 'boolean') return 'boolean'
  if (jsonType === 'integer' || jsonType === 'number') return 'number'
  if (name === 'path') return 'image'
  if (/prompt|instruction|hint/i.test(name)) return 'textarea'
  return 'text'
}

/** One typed param field, widget picked from the node type's own JSON schema (T29 item 3):
 * a select for an enum, a number input for int/number, a checkbox for bool, a textarea for
 * anything prompt/instruction/hint-shaped, a text input + "pick an existing image" select
 * for a `path` field (source.file's asset ref), else a plain text input. */
function ParamField({
  name, prop, value, imageAssets, onChange,
}: {
  name: string
  prop: JSONSchemaProp
  value: unknown
  imageAssets: string[]
  onChange: (v: unknown) => void
}) {
  const widget = widgetFor(name, prop)
  const label = prop.title ?? name
  const testId = `graph-field-${name}`
  if (widget === 'select') {
    return (
      <label className="block mt-1">
        <div>{label}</div>
        <select data-testid={testId} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
          {(prop.enum ?? []).map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </label>
    )
  }
  if (widget === 'boolean') {
    return (
      <label className="block mt-1">
        <input type="checkbox" data-testid={testId} checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} /> {label}
      </label>
    )
  }
  if (widget === 'number') {
    return (
      <label className="block mt-1">
        <div>{label}</div>
        <input type="number" data-testid={testId} value={typeof value === 'number' ? value : 0} onChange={(e) => onChange(Number(e.target.value))} />
      </label>
    )
  }
  if (widget === 'textarea') {
    return (
      <label className="block mt-1">
        <div>{label}</div>
        <textarea data-testid={testId} rows={2} className="w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
      </label>
    )
  }
  if (widget === 'image') {
    return (
      <label className="block mt-1">
        <div>{label} (image path)</div>
        <input data-testid={testId} className="w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
        {imageAssets.length > 0 && (
          <select data-testid={`${testId}-pick`} defaultValue="" onChange={(e) => e.target.value && onChange(e.target.value)}>
            <option value="" disabled>pick an existing image…</option>
            {imageAssets.map((url) => (
              <option key={url} value={url}>{url.split('/').pop()}</option>
            ))}
          </select>
        )}
      </label>
    )
  }
  return (
    <label className="block mt-1">
      <div>{label}</div>
      <input data-testid={testId} className="w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}

/** T29 rebuild of T28's inspector: a typed form (Save/Cancel) driven by the node type's own
 * `params_schema`, a model-swap select for spending node types (applies immediately -- a
 * model change isn't a "draft" the way a param edit is), labelled inputs/outputs showing
 * what each is wired to, and Delete/Duplicate. Raw JSON moves under "Advanced". */
export function GraphInspector({
  selectedNode, selectedStatus, selectedType, workflow, registry, artifacts,
  onDisconnect, onRunFromHere, onSaveParams, onDelete, onDuplicate, onRefreshModels,
}: Props) {
  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const [saving, setSaving] = useState(false)
  // Content, not reference: `selectedNode` is rebuilt from `workflow.nodes.find(...)` on
  // every poll/SSE refresh, so its `.params` object is a *new reference* even when nothing
  // changed -- resetting the draft on reference alone would stomp an in-progress edit every
  // few seconds. Resetting on content instead only fires when the server's own value really
  // moved (a save landing, a poll picking up someone else's change, or the model-swap select
  // below, which saves immediately and legitimately invalidates any unsaved draft here).
  const paramsKey = JSON.stringify(selectedNode?.params ?? {})

  useEffect(() => {
    setDraft(selectedNode?.params ?? {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNode?.id, paramsKey])

  if (!selectedNode) {
    return (
      <div className="graph-inspector" style={{ width: 280, padding: 10, fontSize: 11, overflowY: 'auto' }} data-testid="graph-inspector">
        <div className="graph-inspector-label">Click a node to inspect it.</div>
      </div>
    )
  }

  const schema = (selectedType?.params_schema ?? {}) as JSONSchema
  const properties = schema.properties ?? {}
  const dirty = JSON.stringify(draft) !== JSON.stringify(selectedNode.params)
  const hasModelPicker = selectedNode.type_id in MODEL_KIND
  const imageAssets = Array.from(artifacts.values())
    .flatMap((art) => art.outputs)
    .map((o) => o.url)
    .filter((u): u is string => typeof u === 'string')

  async function save() {
    setSaving(true)
    try {
      await onSaveParams(selectedNode!.id, draft)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="graph-inspector" style={{ width: 280, padding: 10, fontSize: 11, overflowY: 'auto' }} data-testid="graph-inspector">
      <div style={{ fontWeight: 600 }}>{humanNodeName(selectedNode.type_id)}</div>
      <div className="graph-inspector-label" data-testid="graph-inspector-state">
        {stateText(selectedNode.type_id, selectedStatus?.state ?? 'unresolved', selectedStatus?.fail_cause)}
      </div>

      {selectedType && (
        <div className="mt-2 graph-inspector-label">
          <div style={{ fontWeight: 600 }}>Inputs</div>
          {(selectedType.inputs as { name?: string; required?: boolean }[]).length === 0 && <div>—</div>}
          {(selectedType.inputs as { name?: string; required?: boolean }[]).map((i) => {
            const wired = workflow?.edges.filter((e) => e.to_node === selectedNode.id && e.to_input === i.name) ?? []
            const from = wired.map((e) => humanNodeName(workflow!.nodes.find((n) => n.id === e.from_node)?.type_id ?? e.from_node))
            return (
              <div key={i.name}>
                {i.name}: {from.length > 0 ? from.join(', ') : i.required ? 'not wired (required)' : 'not wired'}
              </div>
            )
          })}
          <div className="mt-1" style={{ fontWeight: 600 }}>Outputs</div>
          {(selectedType.outputs as { name?: string }[]).length === 0 && <div>—</div>}
          {(selectedType.outputs as { name?: string }[]).map((o) => {
            const wired = workflow?.edges.filter((e) => e.from_node === selectedNode.id && e.from_output === o.name) ?? []
            const to = wired.map((e) => humanNodeName(workflow!.nodes.find((n) => n.id === e.to_node)?.type_id ?? e.to_node))
            return (
              <div key={o.name}>
                {o.name}: {to.length > 0 ? to.join(', ') : 'unused'}
              </div>
            )
          })}
        </div>
      )}

      {hasModelPicker && (
        <ModelPicker
          typeId={selectedNode.type_id}
          model={String(selectedNode.params.model ?? '')}
          registry={registry}
          onChange={(modelId) => onSaveParams(selectedNode.id, { ...selectedNode.params, model: modelId })}
          onRefresh={onRefreshModels}
        />
      )}

      <div className="mt-2" data-testid="graph-typed-fields">
        <div style={{ fontWeight: 600 }}>Params</div>
        {Object.entries(properties)
          .filter(([name]) => name !== 'model')
          .map(([name, prop]) => (
            <ParamField
              key={name}
              name={name}
              prop={prop}
              value={draft[name]}
              imageAssets={imageAssets}
              onChange={(v) => setDraft((d) => ({ ...d, [name]: v }))}
            />
          ))}
        <div className="mt-1 flex gap-2">
          <button type="button" className="underline" data-testid="graph-params-save" disabled={!dirty || saving} onClick={save}>
            Save
          </button>
          <button type="button" className="underline" data-testid="graph-params-cancel" disabled={!dirty} onClick={() => setDraft(selectedNode.params)}>
            Cancel
          </button>
        </div>
      </div>

      <details className="mt-2">
        <summary style={{ cursor: 'pointer' }}>Advanced</summary>
        <pre className="mt-1 whitespace-pre-wrap break-all rounded" style={{ padding: 6 }}>
          {JSON.stringify(selectedNode.params, null, 1)}
        </pre>
      </details>

      <button type="button" className="underline mt-2 block" data-testid="graph-run-from-here" onClick={onRunFromHere}>
        Run from here
      </button>

      <div className="mt-2 flex gap-2">
        <button type="button" className="underline" data-testid="graph-delete-node" onClick={onDelete}>
          Delete node
        </button>
        <button type="button" className="underline" data-testid="graph-duplicate-node" onClick={onDuplicate}>
          Duplicate
        </button>
      </div>

      <div className="mt-2">
        <div style={{ fontWeight: 600 }}>Edges here</div>
        {workflow?.edges
          .filter((e) => e.from_node === selectedNode.id || e.to_node === selectedNode.id)
          .map((e) => (
            <div key={e.id} className="flex justify-between items-center">
              <span className="graph-inspector-label">
                {humanNodeName(workflow.nodes.find((n) => n.id === e.from_node)?.type_id ?? e.from_node)} {'→'}{' '}
                {humanNodeName(workflow.nodes.find((n) => n.id === e.to_node)?.type_id ?? e.to_node)}
              </span>
              <button type="button" className="underline" data-testid="graph-disconnect" onClick={() => onDisconnect(e.id)}>
                x
              </button>
            </div>
          ))}
      </div>
    </div>
  )
}
