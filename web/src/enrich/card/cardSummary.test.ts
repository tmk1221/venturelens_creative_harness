import { describe, expect, it } from 'vitest'
import type { NodeStatus } from '../types'
import { headerNode, videoFrameLabel } from './cardSummary'

function node(id: string, type_id: string, state: NodeStatus['state'], fail_cause: string | null = null): NodeStatus {
  return { id, type_id, state, input_hash: null, selected: null, outputs: [], fail_cause }
}

describe('T37 card summary', () => {
  it('says when the video was generated at another aspect and cropped', () => {
    expect(videoFrameLabel({ aspect: '9:16', crop_to: '4:5' })).toBe('generated 9:16, cropped to 4:5')
    expect(videoFrameLabel({ aspect: '9:16', crop_to: null })).toBe('9:16')
    expect(videoFrameLabel({})).toBeNull()
    expect(videoFrameLabel(undefined)).toBeNull()
  })

  it('puts a failed node (and its one-sentence cause) in the card header', () => {
    const nodes = [
      node('b1-video', 'video.generate', 'done'),
      node('b1-verify', 'asset.verify', 'failed', 'The clip is 30 fps but the project is 23.976 fps.'),
      node('b1-approve', 'human.approve', 'needs_approval'),
    ]
    const byId = new Map(nodes.map((n) => [n.id, n]))
    expect(headerNode(nodes, byId, 'b1')?.fail_cause).toBe('The clip is 30 fps but the project is 23.976 fps.')
    const healthy = nodes.map((n) => (n.state === 'failed' ? { ...n, state: 'done' as const, fail_cause: null } : n))
    expect(headerNode(healthy, new Map(healthy.map((n) => [n.id, n])), 'b1')?.id).toBe('b1-approve')
  })
})
