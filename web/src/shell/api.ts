import { api } from '../api/client'
import { EnrichApiError } from '../enrich/api'
import type { BrandKit, Consent, Decisions, Project } from '../api/types'

/** T30e: the top-bar Decisions view (renamed from the old app's "Needs you") and the jobs
 * drawer's Cancel + consent record actions -- kept separate from `enrich/api.ts` since these
 * are shell-level (project/cut-wide), not one card's own workflow. Same `unwrap`-on-error
 * shape as `enrich/api.ts` so callers get a one-sentence `EnrichApiError.message`. */
function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) {
    const detail = (result.error as { detail?: string; error?: string } | undefined) ?? {}
    throw new EnrichApiError(result.response.status, detail.detail ?? detail.error ?? `request failed (${result.response.status})`)
  }
  return result.data
}

export async function getDecisions(pid: string, cutId: string): Promise<Decisions> {
  const res = await api.GET('/api/projects/{pid}/cuts/{cut_id}/decisions', {
    params: { path: { pid, cut_id: cutId } },
  })
  return unwrap(res as never) as Decisions
}

export async function cancelJob(pid: string, jobId: string) {
  const res = await api.POST('/api/projects/{pid}/queue/{job_id}/cancel', {
    params: { path: { pid, job_id: jobId } },
  })
  return unwrap(res as never)
}

export async function getConsent(pid: string): Promise<Consent> {
  const res = await api.GET('/api/projects/{pid}/consent', { params: { path: { pid } } })
  return unwrap(res as never) as Consent
}

export async function postConsent(pid: string, body: { presenter: string; release_path: string; date: string }): Promise<Consent> {
  const res = await api.POST('/api/projects/{pid}/consent', { params: { path: { pid } }, body })
  return unwrap(res as never) as Consent
}

/** T31: `providers: fake|real` (plus booleans-only key/tool presence -- never a value). */
export async function getDoctor(): Promise<{ providers?: string }> {
  const res = await api.GET('/api/doctor', {})
  return unwrap(res as never) as { providers?: string }
}

/** T33: the project (for its `brand_kit`), every kit it could use, and switching to one. */
export async function getProject(pid: string): Promise<Project> {
  const res = await api.GET('/api/projects/{pid}', { params: { path: { pid } } })
  return unwrap(res as never) as Project
}

/** T39: with `pid`, a library project's company kit (`<Company>/brand/`) comes first. */
export async function listBrandKits(pid?: string): Promise<BrandKit[]> {
  const res = await api.GET('/api/brand-kits', pid ? { params: { query: { project: pid } } } : {})
  return (unwrap(res as never) as { kits: BrandKit[] }).kits
}

export async function setProjectKit(pid: string, brandKit: string): Promise<Project> {
  const res = await api.PATCH('/api/projects/{pid}', { params: { path: { pid } }, body: { brand_kit: brandKit } })
  return unwrap(res as never) as Project
}

/** T42: `presenter` (someone on camera) or `audio_only` (a voice; every second needs a picture). */
export async function setPictureMode(pid: string, pictureMode: Project['picture_mode']): Promise<Project> {
  const res = await api.PATCH('/api/projects/{pid}', { params: { path: { pid } }, body: { picture_mode: pictureMode } })
  return unwrap(res as never) as Project
}
