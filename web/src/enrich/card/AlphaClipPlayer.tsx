import type { CSSProperties } from 'react'
import type { NodeArtifact, NodeStatus } from '../types'

const CHECKERBOARD_STYLE: CSSProperties = {
  backgroundImage:
    'linear-gradient(45deg, #999 25%, transparent 25%), linear-gradient(-45deg, #999 25%, transparent 25%), ' +
    'linear-gradient(45deg, transparent 75%, #999 75%), linear-gradient(-45deg, transparent 75%, #999 75%)',
  backgroundSize: '16px 16px',
  backgroundPosition: '0 0, 0 8px, 8px -8px, -8px 0px',
  backgroundColor: '#ccc',
}

/** T30 "Additions": alpha-aware in-app playback -- an overlay's rendered clip (alpha video)
 * plays over a checkerboard so transparency reads as transparency, not black. Used in place
 * of the plain `<video>` `ClipPlayer` for any `layer === 'overlay'` card. */
export function AlphaClipPlayer({ node, artifacts }: { node: NodeStatus; artifacts: Map<string, NodeArtifact> }) {
  const art = artifacts.get(node.id)
  const video = art?.outputs.find((o) => o.url)
  if (!video?.url) return null
  return (
    <div style={CHECKERBOARD_STYLE} className="rounded overflow-hidden" data-testid="enrich-alpha-clip-bg">
      <video data-testid="enrich-clip" src={video.url} controls className="w-full rounded" />
    </div>
  )
}
