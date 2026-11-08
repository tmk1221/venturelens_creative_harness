import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Project } from '../api/types'
import { getProject, setPictureMode } from '../shell/api'
import { PictureModeSetting } from './PictureModeSetting'

/** T42: the project's picture mode on the Ingest page; API mocked. */
vi.mock('../shell/api', () => ({ getProject: vi.fn(), setPictureMode: vi.fn() }))

function project(mode: Project['picture_mode']): Project {
  return { id: 'p1', name: 'Sample', root: '/tmp/p1', schema_version: 1, brand_kit: 'show', picture_mode: mode }
}

beforeEach(() => {
  vi.mocked(getProject).mockReset().mockResolvedValue(project('presenter'))
  vi.mocked(setPictureMode).mockReset()
})

describe('PictureModeSetting', () => {
  it("shows the project's mode and switches to audio only", async () => {
    vi.mocked(setPictureMode).mockResolvedValue(project('audio_only'))
    render(<PictureModeSetting pid="p1" />)
    const presenter = (await screen.findByTestId('picture-mode-presenter')) as HTMLInputElement
    expect(presenter.checked).toBe(true)
    fireEvent.click(screen.getByTestId('picture-mode-audio_only'))
    await waitFor(() => expect(setPictureMode).toHaveBeenCalledWith('p1', 'audio_only'))
    await waitFor(() => expect((screen.getByTestId('picture-mode-audio_only') as HTMLInputElement).checked).toBe(true))
  })

  it('a refused change keeps the current mode and says why', async () => {
    vi.mocked(setPictureMode).mockRejectedValue(new Error('server said no'))
    render(<PictureModeSetting pid="p1" />)
    fireEvent.click(await screen.findByTestId('picture-mode-audio_only'))
    expect(await screen.findByTestId('picture-mode-error')).toHaveTextContent('server said no')
    expect((screen.getByTestId('picture-mode-presenter') as HTMLInputElement).checked).toBe(true)
  })
})
