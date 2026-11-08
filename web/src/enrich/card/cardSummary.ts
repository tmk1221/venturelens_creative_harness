import type { NodeStatus } from '../types'

/** T37: how a live-action beat's video frame reads on its card -- the cut's aspect ("4:5"),
 * or "generated 9:16, cropped to 4:5" when the video model didn't offer it (the
 * `video.generate` node's `aspect` + `crop_to` params, set at instantiate time). */
export function videoFrameLabel(params: Record<string, unknown> | undefined): string | null {
  const aspect = typeof params?.aspect === 'string' ? params.aspect : null
  const cropTo = typeof params?.crop_to === 'string' ? params.crop_to : null
  if (!aspect) return null
  return cropTo && cropTo !== aspect ? `generated ${aspect}, cropped to ${cropTo}` : aspect
}

/** The node whose state the card header shows: any failed node first, so its one-sentence
 * cause (T37: e.g. asset.verify's "The clip is 30 fps but the project is 23.976 fps.") is on
 * the card, not only in the graph; else the beat's final approve, else its video. */
export function headerNode(nodes: NodeStatus[], nodesById: Map<string, NodeStatus>, bid: string): NodeStatus | undefined {
  return nodes.find((n) => n.state === 'failed')
    ?? nodesById.get(`${bid}-approve-final`) ?? nodesById.get(`${bid}-approve`) ?? nodesById.get(`${bid}-video`)
}
