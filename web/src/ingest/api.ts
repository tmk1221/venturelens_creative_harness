import { api } from '../api/client'
import type {
  BrandPage, IngestJob, IngestSource, IngestStatus, Library, NewProjectRequest, NewProjectResult, OpenEditorResult, TranscribeEstimate, TranscribeJob,
} from '../api/types'

/** T34: the Ingest page's calls. Every failure throws an `IngestApiError` whose message is the
 * server's own plain sentence (`detail`), e.g. "The project folder … is inside the footage folder". */
export class IngestApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || result.data === undefined) {
    const body = (result.error as { detail?: unknown; error?: string } | undefined) ?? {}
    const detail = typeof body.detail === 'string' ? body.detail : body.error
    throw new IngestApiError(result.response.status, detail ?? `Request failed (${result.response.status})`)
  }
  return result.data
}

export async function createProject(body: NewProjectRequest): Promise<NewProjectResult> {
  return unwrap(await api.POST('/api/projects/new', { body }))
}

/** T39: the media library's companies (and their projects), for the New project page. */
export async function getLibrary(): Promise<Library> {
  return unwrap(await api.GET('/api/library', {}))
}

export async function getIngestStatus(pid: string): Promise<IngestStatus> {
  return unwrap(await api.GET('/api/projects/{pid}/ingest/status', { params: { path: { pid } } }))
}

export async function rerunIngest(pid: string): Promise<IngestJob> {
  return unwrap(await api.POST('/api/projects/{pid}/ingest/run', { params: { path: { pid } } }))
}

export async function importTranscript(pid: string, syncGroupId: string, path: string): Promise<IngestSource> {
  return unwrap(
    await api.POST('/api/projects/{pid}/ingest/transcript', {
      params: { path: { pid } },
      body: { sync_group_id: syncGroupId, path },
    }),
  )
}

export async function openEditor(pid: string): Promise<OpenEditorResult> {
  return unwrap(await api.POST('/api/projects/{pid}/ingest/open-editor', { params: { path: { pid } } }))
}

/** T35: what transcribing one recording would cost (its audio proxy's minutes x the Deepgram rate). */
export async function getTranscribeEstimate(pid: string, syncGroupId: string): Promise<TranscribeEstimate> {
  return unwrap(
    await api.GET('/api/projects/{pid}/ingest/transcribe/estimate', {
      params: { path: { pid }, query: { sync_group_id: syncGroupId } },
    }),
  )
}

/** T31/T35: the one budget a confirmed click creates, capped at exactly the shown estimate. */
export async function createBudget(pid: string, budgetId: string, cap: number, unit: string): Promise<unknown> {
  return unwrap(await api.PUT('/api/projects/{pid}/budgets/{budget_id}', { params: { path: { pid, budget_id: budgetId } }, body: { cap, unit } }))
}

/** Queue the transcription against that budget (202); its progress streams over SSE. */
export async function startTranscription(pid: string, syncGroupId: string, budget: string): Promise<TranscribeJob> {
  return unwrap(
    await api.POST('/api/projects/{pid}/ingest/transcribe', {
      params: { path: { pid } },
      body: { sync_group_id: syncGroupId, provider: 'deepgram', budget, by: 'web' },
    }),
  )
}

/** T41: which kit the project uses and its current signature (changes when a kit file does). */
export async function getBrandPage(pid: string): Promise<BrandPage> {
  return unwrap(await api.GET('/api/projects/{pid}/brand', { params: { path: { pid } } }))
}
