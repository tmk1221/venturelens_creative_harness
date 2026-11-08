import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listBrandKits } from '../shell/api'
import { createProject, getLibrary, IngestApiError } from './api'
import { NewProjectPage } from './NewProjectPage'

/** T34/T39: the New project form -- what it sends (library company/project, or another folder),
 * and a server refusal shown in its own words. */
vi.mock('./api', async (orig) => ({ ...(await orig<typeof import('./api')>()), createProject: vi.fn(), getLibrary: vi.fn() }))
vi.mock('../shell/api', () => ({ listBrandKits: vi.fn() }))

beforeEach(() => {
  vi.mocked(createProject).mockReset()
  vi.mocked(listBrandKits).mockReset().mockResolvedValue([
    { id: 'show', name: 'Sample Weekly Show', status: 'guessed', counts: null, error: null },
  ])
  vi.mocked(getLibrary).mockReset().mockResolvedValue({
    root: '/Volumes/MediaDrive', exists: true,
    companies: [{ name: 'Sample Weekly Show', has_brand: true, projects: ['Show36'] }],
  })
})

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/new']}>
      <Routes>
        <Route path="/new" element={<NewProjectPage />} />
        <Route path="/p/:pid/ingest" element={<div data-testid="ingest-route" />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function fill(root: string) {
  fireEvent.click(screen.getByTestId('np-where-folder'))
  fireEvent.change(screen.getByTestId('np-name'), { target: { value: 'Show 37 Sample' } })
  fireEvent.change(screen.getByTestId('np-root'), { target: { value: root } })
  fireEvent.change(screen.getByTestId('np-sources'), { target: { value: '/Volumes/MediaDrive/show/37.mp4\n\n' } })
  await screen.findByRole('option', { name: 'Sample Weekly Show (guessed — review)' })
  fireEvent.change(screen.getByTestId('np-kit'), { target: { value: 'show' } })
  fireEvent.click(screen.getByTestId('np-submit'))
}

describe('NewProjectPage', () => {
  it('sends the form (folder defaults under ~/Post) and opens the Ingest page', async () => {
    vi.mocked(createProject).mockResolvedValue({ project: { id: 'p9', root: '/Users/t/Post/show-37-keith', name: 'Show 37 Sample' }, job_id: 'j1' })
    renderPage()
    await fill('')
    await screen.findByTestId('ingest-route')
    expect(createProject).toHaveBeenCalledWith({
      name: 'Show 37 Sample', root: '~/Post/show-37-keith', copy_sources: false, sources: ['/Volumes/MediaDrive/show/37.mp4'], transcripts: [], brand_kit: 'show',
    })
  })

  it("shows the server's refusal in plain words and stays on the form", async () => {
    const msg = 'The project folder /x/Video/source/post is inside the footage folder /x/Video/source.'
    vi.mocked(createProject).mockRejectedValue(new IngestApiError(400, msg))
    renderPage()
    await fill('/x/Video/source/post')
    await waitFor(() => expect(screen.getByTestId('np-error')).toHaveTextContent(msg))
    expect(screen.queryByTestId('ingest-route')).not.toBeInTheDocument()
  })

  it('puts a library project under its company, as the Resolve project name', async () => {
    vi.mocked(createProject).mockResolvedValue({ project: { id: 'p7', root: '/Volumes/MediaDrive/Sample Weekly Show/Show37', name: 'Show37' }, job_id: 'j2' })
    renderPage()
    await screen.findByRole('option', { name: 'Sample Weekly Show (brand kit)' })
    expect(screen.getByTestId('np-submit')).toBeDisabled()
    fireEvent.change(screen.getByTestId('np-company'), { target: { value: 'Sample Weekly Show' } })
    fireEvent.change(screen.getByTestId('np-name'), { target: { value: 'Show37' } })
    fireEvent.change(screen.getByTestId('np-sources'), { target: { value: '/Users/t/Downloads/37.mp4' } })
    fireEvent.click(screen.getByTestId('np-copy'))
    expect(screen.getByTestId('np-library-path')).toHaveTextContent('/Volumes/MediaDrive/Sample Weekly Show/Show37/')
    fireEvent.click(screen.getByTestId('np-submit'))
    await screen.findByTestId('ingest-route')
    expect(createProject).toHaveBeenCalledWith({
      name: 'Show37', company: 'Sample Weekly Show', copy_sources: true, sources: ['/Users/t/Downloads/37.mp4'],
      transcripts: [], brand_kit: null,
    })
  })

  it('takes a new company by name', async () => {
    vi.mocked(createProject).mockResolvedValue({ project: { id: 'p8', root: '/x', name: 'Launch' }, job_id: 'j3' })
    renderPage()
    await screen.findByRole('option', { name: 'New company…' })
    fireEvent.change(screen.getByTestId('np-company'), { target: { value: '__new__' } })
    fireEvent.change(screen.getByTestId('np-new-company'), { target: { value: 'Acme Co' } })
    fireEvent.change(screen.getByTestId('np-name'), { target: { value: 'Launch' } })
    fireEvent.change(screen.getByTestId('np-sources'), { target: { value: '/a.mp4' } })
    fireEvent.click(screen.getByTestId('np-submit'))
    await screen.findByTestId('ingest-route')
    expect(vi.mocked(createProject).mock.calls[0][0]).toMatchObject({ company: 'Acme Co', copy_sources: false })
  })
})
