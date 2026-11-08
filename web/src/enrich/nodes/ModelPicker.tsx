import { useState } from 'react'
import { MODEL_KIND, priceLabel } from '../graphMeta'
import type { ModelOption, NodeRegistry } from '../types'

/** T30d spec: "Model picker INSIDE `still.generate`/`video.generate`/`endframe.generate`
 * nodes: a select at the top of the node listing models from the registry with price/credit
 * badge and capability chips ... changing it re-shapes params and marks the node stale."
 * Re-shaping/staleness are both free: `model` is just another param, so saving it through
 * `onPatchParams` gives the node a new `input_hash` (`graph.hashing`) the same way any other
 * param edit does -- nothing here needs to know what "stale" means. Reused by
 * `GraphInspector`'s own model select so the in-node and inspector pickers never drift.
 * T39: every image/video model Higgsfield lists, by its display name (`nano_banana_2` reads
 * "Nano Banana Pro"); the inspector's picker has a refresh button that re-lists them. */
export function ModelPicker({
  typeId, model, registry, onChange, compact, onRefresh,
}: {
  typeId: string
  model: string
  registry: NodeRegistry | null
  onChange: (modelId: string) => void
  /** In-node card: tiny, no label. Inspector: full width with a label. */
  compact?: boolean
  /** Inspector only: re-list the models (`POST .../models/refresh`). */
  onRefresh?: () => Promise<void>
}) {
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const kind = MODEL_KIND[typeId]
  const options: ModelOption[] = kind ? (registry?.models ?? []).filter((m) => m.kind === kind) : []
  if (options.length === 0) return null
  const selected = options.find((m) => m.id === model)

  return (
    <div className={compact ? 'graph-node-model' : 'mt-2'} data-testid="node-model-picker">
      {!compact && (
        <div style={{ fontWeight: 600 }}>
          Model
          {onRefresh && (
            <button
              type="button" data-testid="graph-model-refresh" disabled={refreshing} style={{ marginLeft: 8, fontWeight: 400 }}
              onClick={() => {
                setRefreshing(true)
                setRefreshError(null)
                onRefresh()
                  .catch((e: unknown) => setRefreshError(e instanceof Error ? e.message : 'Could not refresh the models'))
                  .finally(() => setRefreshing(false))
              }}
            >
              {refreshing ? 'Refreshing…' : 'Refresh list'}
            </button>
          )}
        </div>
      )}
      {refreshError && <div data-testid="graph-model-refresh-error" style={{ color: '#b3261e' }}>{refreshError}</div>}
      <select
        // The inspector's own select keeps the pre-T30d `graph-model-select` id (the
        // existing enrich e2e selects exactly one via `getByTestId`); the in-node picker
        // renders a second `<select>` for the *same* node whenever it's also selected, so it
        // needs its own id to keep that a single-match query.
        data-testid={compact ? 'graph-node-model-select' : 'graph-model-select'}
        className={compact ? 'graph-node-model-select' : undefined}
        value={model}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => {
          e.stopPropagation()
          onChange(e.target.value)
        }}
      >
        {options.map((m) => (
          <option key={m.id} value={m.id} title={m.id}>{m.label || m.id} — {priceLabel(m.pricing)}</option>
        ))}
      </select>
      {selected && selected.capabilities.length > 0 && (
        <div className="graph-node-chips" data-testid="graph-model-capabilities">
          {selected.capabilities.map((c) => (
            <span key={c} className="graph-node-chip">{c}</span>
          ))}
        </div>
      )}
    </div>
  )
}
