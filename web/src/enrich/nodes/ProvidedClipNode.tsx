import type { ProvidedClip } from '../types'

/** T30d: `provided.clip`'s in-node body -- "browse project sources/assets, set in/out --
 * sources come from the project's `provided/` folder catalogue; for the demo, seed 3 fake
 * clips." `GET .../provided-catalogue` (fixture-backed, see `routes/enrich.py`) is that
 * catalogue; picking one sets `path` and resets `in_seconds`/`out_seconds` to the clip's
 * full range, then the two number inputs trim it. */
export function ProvidedClipNode({
  path, inSeconds, outSeconds, clips, onPatchParams,
}: {
  path: string
  inSeconds: number
  outSeconds: number | null
  clips: ProvidedClip[]
  onPatchParams: (params: Record<string, unknown>) => void
}) {
  const chosen = clips.find((c) => c.path === path)

  return (
    <div className="graph-node-provided" data-testid="node-provided-clip" onClick={(e) => e.stopPropagation()}>
      <select
        data-testid="graph-provided-select"
        value={path}
        onChange={(e) => {
          const clip = clips.find((c) => c.path === e.target.value)
          if (clip) onPatchParams({ path: clip.path, in_seconds: 0, out_seconds: clip.duration_seconds })
        }}
      >
        <option value="" disabled>pick a clip…</option>
        {clips.map((c) => (
          <option key={c.path} value={c.path}>{c.label} ({c.duration_seconds}s)</option>
        ))}
      </select>
      {chosen && (
        <div className="graph-node-provided-trim">
          <label>
            in
            <input
              data-testid="graph-provided-in"
              type="number" min={0} step={0.1} value={inSeconds}
              onChange={(e) => onPatchParams({ path, in_seconds: Number(e.target.value), out_seconds: outSeconds })}
            />
          </label>
          <label>
            out
            <input
              data-testid="graph-provided-out"
              type="number" min={0} step={0.1} value={outSeconds ?? chosen.duration_seconds}
              onChange={(e) => onPatchParams({ path, in_seconds: inSeconds, out_seconds: Number(e.target.value) })}
            />
          </label>
        </div>
      )}
    </div>
  )
}
