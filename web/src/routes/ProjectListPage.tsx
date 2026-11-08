import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useProjectStore } from '../store/projectStore'

export function ProjectListPage() {
  const projects = useProjectStore((s) => s.projects)
  const fetchProjects = useProjectStore((s) => s.fetchProjects)
  const addProject = useProjectStore((s) => s.addProject)
  const [root, setRoot] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    void fetchProjects()
  }, [fetchProjects])

  return (
    <div className="p-6 max-w-2xl mx-auto w-full">
      <div className="flex items-baseline justify-between mb-4">
        <h1 className="text-lg font-medium">Projects</h1>
        <Link to="/new" data-testid="new-project-link" className="text-sm underline">
          New project from a recording
        </Link>
      </div>
      <ul data-testid="project-list" className="mb-6">
        {projects.map((p) => (
          <li key={p.id} className="border-b border-neutral-100 dark:border-neutral-900">
            <button
              type="button"
              className="w-full text-left py-2 hover:bg-neutral-50 dark:hover:bg-neutral-900"
              onClick={() => navigate(`/p/${p.id}/edit`)}
            >
              <span className="font-medium">{p.name}</span>
              <span className="ml-2 text-neutral-500">{p.root}</span>
            </button>
          </li>
        ))}
      </ul>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (!root.trim()) return
          void addProject(root.trim()).then((p) => {
            if (p) navigate(`/p/${p.id}/edit`)
          })
        }}
      >
        <input
          data-testid="project-root-input"
          value={root}
          onChange={(e) => setRoot(e.target.value)}
          placeholder="/path/to/project"
          className="flex-1 border border-neutral-300 dark:border-neutral-700 rounded px-2 py-1 bg-transparent"
        />
        <button type="submit" className="border border-neutral-300 dark:border-neutral-700 rounded px-3 py-1">
          Open
        </button>
      </form>
    </div>
  )
}
