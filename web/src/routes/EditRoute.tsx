import { useEffect, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { EditWorkspace } from '../edit/EditWorkspace'

/** `/p/:pid/edit` with no cut id yet: picks (or creates nothing -- just redirects to) the
 * first existing cut, so `EditWorkspace` always has a concrete `cutId` in its URL. */
export function EditRoute() {
  const { pid } = useParams<{ pid: string }>()
  const [cutId, setCutId] = useState<string | null | undefined>(undefined)

  useEffect(() => {
    if (!pid) return
    void api.GET('/api/projects/{pid}/cuts', { params: { path: { pid } } }).then(({ data }) => {
      setCutId(data && data.length > 0 ? data[0]!.id : null)
    })
  }, [pid])

  if (!pid) return null
  if (cutId === undefined) return <div className="p-6 text-neutral-500">Loading…</div>
  if (cutId === null) {
    return (
      <div className="p-6 text-neutral-500">
        No cuts yet in this project. <Link to={`/p/${pid}/ingest`} className="underline">Go to Ingest</Link> to add a
        transcript and open the editor.
      </div>
    )
  }
  return <Navigate to={`/p/${pid}/edit/${cutId}`} replace />
}

export function EditWorkspaceRoute() {
  return <EditWorkspace />
}
