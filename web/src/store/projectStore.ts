import { create } from 'zustand'
import { api } from '../api/client'
import type { ProjectRef } from '../api/types'

interface ProjectState {
  projects: ProjectRef[]
  loading: boolean
  error: string | null
  fetchProjects: () => Promise<void>
  addProject: (root: string, name?: string) => Promise<ProjectRef | null>
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  loading: false,
  error: null,
  fetchProjects: async () => {
    set({ loading: true, error: null })
    const { data, error } = await api.GET('/api/projects')
    if (error) {
      set({ loading: false, error: 'Failed to load projects' })
      return
    }
    set({ projects: data.projects, loading: false })
  },
  addProject: async (root, name) => {
    const { data, error } = await api.POST('/api/projects', { body: { root, name } })
    if (error || !data) {
      set({ error: 'Failed to add project' })
      return null
    }
    set((s) => ({ projects: [...s.projects.filter((p) => p.id !== data.id), data] }))
    return data
  },
}))
