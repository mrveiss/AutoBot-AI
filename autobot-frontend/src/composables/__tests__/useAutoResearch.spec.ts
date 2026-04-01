// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useAutoResearch } from '../useAutoResearch'

const mockGet = vi.fn()
const mockPost = vi.fn()

vi.mock('../useApi', () => ({
  useApi: () => ({
    get: mockGet,
    post: mockPost,
  }),
}))

describe('useAutoResearch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Re-apply mocks (mockReset: true wipes vi.mock factories)
    mockGet.mockReset()
    mockPost.mockReset()
  })

  it('fetchExperiments populates experiments ref', async () => {
    mockGet.mockResolvedValue({
      experiments: [{ id: 'e1', state: 'completed', hypothesis: 'test' }],
    })

    const { experiments, fetchExperiments } = useAutoResearch()
    await fetchExperiments()

    expect(experiments.value).toHaveLength(1)
    expect(experiments.value[0].id).toBe('e1')
  })

  it('fetchStats populates stats ref', async () => {
    mockGet.mockResolvedValue({
      total_experiments: 10,
      kept: 3,
      best_val_bpb: 4.5,
    })

    const { stats, fetchStats } = useAutoResearch()
    await fetchStats()

    expect(stats.value).not.toBeNull()
    expect(stats.value!.total_experiments).toBe(10)
  })

  it('approveExperiment sends correct request', async () => {
    mockPost.mockResolvedValue({})
    mockGet.mockResolvedValue({ approvals: [] })

    const { approveExperiment } = useAutoResearch()
    await approveExperiment('s1', 'e1')

    expect(mockPost).toHaveBeenCalledWith(
      '/api/autoresearch/approvals/s1/e1',
      { decision: 'approved' },
    )
  })
})
