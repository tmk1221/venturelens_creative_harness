import { useState } from 'react'
import { CHARACTER_PATH_PREFIX } from '../graphMeta'
import type { CastEntry } from '../types'

/** T30d "character node": a plain `source.file` node (image-typed, so it wires into
 * `still.generate`'s "continuity" input exactly like the "Reference image" palette entry --
 * see `graphMeta.ts`'s `PALETTE` docstring for why it isn't a distinct backend node type)
 * whose `path` the user fills in by picking a name from the project's cast registry (T12)
 * instead of typing a raw path. Detected by `CHARACTER_PATH_PREFIX` on `params.path`.
 *
 * A picked cast member's own `anchor_asset_path` becomes the node's `path` when the entry
 * has one; an entry with no anchor yet (nothing approved to point at) keeps the `cast/{name}`
 * placeholder so the choice is still visible on the card, but `still.generate`'s own
 * `continuity_names` pre-check (`recipes.instantiate._check_cast`) is what actually blocks a
 * beat on an unready anchor -- this node doesn't duplicate that logic. */
export function CharacterNode({
  path, castList, onPatchParams, onCreateCastEntry,
}: {
  path: string
  castList: CastEntry[]
  onPatchParams: (params: Record<string, unknown>) => void
  onCreateCastEntry: (name: string) => Promise<CastEntry>
}) {
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false)
  const chosenName = path.startsWith(CHARACTER_PATH_PREFIX) ? path.slice(CHARACTER_PATH_PREFIX.length) : ''

  function pick(entry: CastEntry) {
    onPatchParams({ path: entry.anchor_asset_path || `${CHARACTER_PATH_PREFIX}${entry.name}`, handle_type: 'image' })
  }

  async function createAndPick() {
    const name = newName.trim()
    if (!name || busy) return
    setBusy(true)
    try {
      const entry = await onCreateCastEntry(name)
      pick(entry)
      setNewName('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="graph-node-character" data-testid="node-character-picker" onClick={(e) => e.stopPropagation()}>
      {castList.length > 0 && (
        <select
          data-testid="graph-character-select"
          value={chosenName}
          onChange={(e) => {
            const entry = castList.find((c) => c.name === e.target.value)
            if (entry) pick(entry)
          }}
        >
          <option value="" disabled>pick a character…</option>
          {castList.map((c) => (
            <option key={c.id} value={c.name}>{c.name}{c.anchor_ready ? '' : ' (no anchor yet)'}</option>
          ))}
        </select>
      )}
      <div className="graph-node-character-new">
        <input
          data-testid="graph-character-new-name"
          placeholder="new character name…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button type="button" data-testid="graph-character-new-add" disabled={busy || !newName.trim()} onClick={createAndPick}>
          Add
        </button>
      </div>
    </div>
  )
}
