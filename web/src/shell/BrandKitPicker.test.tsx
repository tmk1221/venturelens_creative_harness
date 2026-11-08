import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BrandKit, Project } from '../api/types'
import { EnrichApiError } from '../enrich/api'
import { getProject, listBrandKits, setProjectKit } from './api'
import { BrandKitPicker } from './BrandKitPicker'

/** T33: the shell's brand kit picker -- the project's kit (`GET /api/projects/{pid}`), every
 * kit with its status (`GET /api/brand-kits`), and `PATCH` to switch. API mocked here. */
vi.mock('./api', () => ({ getProject: vi.fn(), listBrandKits: vi.fn(), setProjectKit: vi.fn() }))

const KITS: BrandKit[] = [
  { id: '_demo', name: 'Kestrel Demo Co.', status: 'filled', counts: { filled: 25, guessed: 0, pending: 11, total: 36 }, error: null },
  { id: 'show', name: 'Sample Weekly Show', status: 'guessed', counts: { filled: 0, guessed: 23, pending: 12, total: 35 }, error: null },
]

function project(brandKit: string): Project {
  return { id: 'p1', name: 'Sample sample', root: '/tmp/p1', schema_version: 1, brand_kit: brandKit, picture_mode: 'presenter' }
}

beforeEach(() => {
  vi.mocked(getProject).mockReset().mockResolvedValue(project('show'))
  vi.mocked(listBrandKits).mockReset().mockResolvedValue(KITS)
  vi.mocked(setProjectKit).mockReset()
})

describe('BrandKitPicker', () => {
  it("shows the project's kit by name, with no status badge (T41)", async () => {
    render(<BrandKitPicker pid="p1" />)
    const select = (await screen.findByTestId('brand-kit-select')) as HTMLSelectElement
    expect(select.value).toBe('show')
    expect(screen.getByRole('option', { name: 'Sample Weekly Show' })).toBeInTheDocument()
    expect(screen.queryByTestId('brand-kit-status')).toBeNull()
    expect(screen.queryByText('guessed')).toBeNull()
  })

  it('switching kits patches the project', async () => {
    vi.mocked(setProjectKit).mockResolvedValue(project('_demo'))
    render(<BrandKitPicker pid="p1" />)
    const select = await screen.findByTestId('brand-kit-select')
    fireEvent.change(select, { target: { value: '_demo' } })
    await waitFor(() => expect(setProjectKit).toHaveBeenCalled())
    expect(setProjectKit).toHaveBeenCalledWith('p1', '_demo')
    await waitFor(() => expect((screen.getByTestId('brand-kit-select') as HTMLSelectElement).value).toBe('_demo'))
  })

  it('a refused switch keeps the current kit and says why', async () => {
    vi.mocked(setProjectKit).mockRejectedValue(new EnrichApiError(400, "unknown brand kit '_demo'; available: show"))
    render(<BrandKitPicker pid="p1" />)
    const select = await screen.findByTestId('brand-kit-select')
    fireEvent.change(select, { target: { value: '_demo' } })
    expect(await screen.findByTestId('brand-kit-error')).toHaveTextContent('available: show')
    expect((screen.getByTestId('brand-kit-select') as HTMLSelectElement).value).toBe('show')
  })

  it('a kit that does not load says so', async () => {
    vi.mocked(listBrandKits).mockResolvedValue([{ id: 'show', name: 'Sample Weekly Show', status: 'broken', counts: null, error: 'kit.yaml: bad colour' }])
    render(<BrandKitPicker pid="p1" />)
    expect(await screen.findByTestId('brand-kit-broken')).toHaveTextContent('kit.yaml: bad colour')
  })

  it('renders nothing but a quiet note when the kits cannot be loaded', async () => {
    vi.mocked(listBrandKits).mockRejectedValue(new Error('down'))
    render(<BrandKitPicker pid="p1" />)
    expect(await screen.findByTestId('brand-kit-error')).toHaveTextContent('Brand kits unavailable')
    expect(screen.queryByTestId('brand-kit-select')).toBeNull()
  })
})
