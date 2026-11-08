import { useEffect, useState } from 'react'
import * as enrichApi from './api'
import type { NodeArtifact, NodeStatus } from './types'

/** Fetches `.../nodes/{id}/artifact` for every node that has ever built something, so
 * `GraphNode` can show a real thumbnail instead of a placeholder. Split out of GraphPanel so
 * that file stays about layout/state, not data-fetching. */
export function useGraphArtifacts(pid: string, workflowId: string | null, nodes: NodeStatus[]): Map<string, NodeArtifact> {
  const [artifacts, setArtifacts] = useState<Map<string, NodeArtifact>>(new Map())
  const key = nodes.map((n) => `${n.id}:${n.state}`).join(',')

  useEffect(() => {
    if (!workflowId) return
    const doneIds = nodes.filter((n) => n.state === 'done' || n.state === 'needs_approval' || n.state === 'stale').map((n) => n.id)
    let cancelled = false
    Promise.all(doneIds.map((id) => enrichApi.getNodeArtifact(pid, workflowId, id).then((a) => [id, a] as const).catch(() => null))).then((pairs) => {
      if (cancelled) return
      setArtifacts(new Map(pairs.filter((p): p is [string, NodeArtifact] => p !== null)))
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, workflowId, key])

  return artifacts
}
