import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { NodeRegistry } from '../types'
import { ModelPicker } from './ModelPicker'

/** T39: the picker lists every model of the node's kind by Higgsfield's display name, and the
 * inspector's refresh button re-lists them. */
const registry = {
  node_types: [], handle_types: [],
  models: [
    { id: 'nano_banana_2', kind: 'image', label: 'Nano Banana Pro', pricing: { credits_per_call: 2 }, capabilities: ['refs'] },
    { id: 'seedream_v5_pro', kind: 'image', label: 'Seedream 5.0 Pro', pricing: {}, capabilities: [] },
    { id: 'kling3_0', kind: 'video', label: 'Kling v3.0', pricing: { credits_per_second: 2 }, capabilities: [] },
  ],
} as unknown as NodeRegistry

describe('ModelPicker', () => {
  it('lists the kind’s models by display name, default selected', () => {
    render(<ModelPicker typeId="still.generate" model="nano_banana_2" registry={registry} onChange={() => {}} />)
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['Nano Banana Pro — 2 cr/call', 'Seedream 5.0 Pro — —'])
    expect(screen.getByTestId('graph-model-select')).toHaveValue('nano_banana_2')
    expect(screen.queryByTestId('graph-model-refresh')).not.toBeInTheDocument()
  })

  it('refreshes the list from the inspector and reports a failure in words', async () => {
    const onRefresh = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('higgsfield not found'))
    render(<ModelPicker typeId="video.generate" model="kling3_0" registry={registry} onChange={() => {}} onRefresh={onRefresh} />)
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['Kling v3.0 — 2 cr/s'])
    fireEvent.click(screen.getByTestId('graph-model-refresh'))
    await waitFor(() => expect(screen.getByTestId('graph-model-refresh')).toHaveTextContent('Refresh list'))
    fireEvent.click(screen.getByTestId('graph-model-refresh'))
    await screen.findByText('higgsfield not found')
    expect(onRefresh).toHaveBeenCalledTimes(2)
  })
})
