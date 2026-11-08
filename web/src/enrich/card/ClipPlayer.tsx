import type { NodeArtifact, NodeStatus } from '../types'

/** Plain (non-alpha) clip player -- `live_action`'s picture video, and `motion_graphic`'s
 * draft/final renders (opaque full-frame, no checkerboard needed; see `AlphaClipPlayer` for
 * overlay's alpha-aware version). */
export function ClipPlayer({ node, artifacts, testId = 'enrich-clip' }: { node: NodeStatus; artifacts: Map<string, NodeArtifact>; testId?: string }) {
  const art = artifacts.get(node.id)
  const video = art?.outputs.find((o) => o.url)
  if (!video?.url) return null
  return <video data-testid={testId} src={video.url} controls className="w-full rounded" />
}
