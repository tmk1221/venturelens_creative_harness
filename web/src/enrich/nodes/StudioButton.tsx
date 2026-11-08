import { useState } from 'react'

/** T30d: "live HyperFrames studio button on design nodes (fake: opens a placeholder)." Real
 * HyperFrames project launch is out of scope (AGENTS.md: never touch the live skills
 * installation from here) -- the button just opens an in-page placeholder panel naming the
 * node it would edit, so the interaction is wired end to end for a future real studio link. */
export function StudioButton({ nodeId }: { nodeId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="graph-node-studio" data-testid="node-studio" onClick={(e) => e.stopPropagation()}>
      <button type="button" data-testid="graph-open-studio" onClick={() => setOpen(true)}>
        Open Studio
      </button>
      {open && (
        <div className="graph-studio-placeholder" data-testid="graph-studio-placeholder">
          <p>HyperFrames Studio (demo placeholder) — editing composition for {nodeId}</p>
          <button type="button" onClick={() => setOpen(false)}>Close</button>
        </div>
      )}
    </div>
  )
}
