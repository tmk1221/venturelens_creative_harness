import type { NodeArtifact, NodeStatus } from '../types'
import { StateBadge } from './StateBadge'

/** T30b/T30c: a `live_action` beat's optional end frame (`endframe.generate`, wired in only
 * when the brief writer's `recommend_end_frame` flagged it at instantiate time -- there is
 * no post-hoc "add an end frame" toggle in this slice, only display of whatever the recipe
 * already built). Shown between the still grid and the clip player so its picked-frame ->
 * end-frame -> video shape reads top to bottom. */
export function EndFrame({ node, artifact }: { node: NodeStatus; artifact: NodeArtifact | undefined }) {
  const image = artifact?.outputs[0]
  return (
    <div className="flex items-center gap-2" data-testid="enrich-endframe">
      <span className="text-neutral-500">End frame</span>
      <StateBadge typeId={node.type_id} state={node.state} failCause={node.fail_cause} />
      {image?.url && <img src={image.url} alt="End frame" className="w-10 h-10 object-cover rounded" />}
    </div>
  )
}
