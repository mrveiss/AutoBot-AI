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

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  }),
}))

const mockShowSubtleErrorNotification = vi.fn()
vi.mock('@/utils/cacheManagement', () => ({
  showSubtleErrorNotification: (...args: unknown[]) =>
    mockShowSubtleErrorNotification(...args),
}))

describe('useAutoResearch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockReset()
    mockPost.mockReset()
    mockShowSubtleErrorNotification.mockReset()
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

  it('fetchExperiments sets error ref and shows notification on failure', async () => {
    mockGet.mockRejectedValue(new Error('network timeout'))

    const { error, fetchExperiments } = useAutoResearch()
    await fetchExperiments()

    expect(error.value).toBe('network timeout')
    expect(mockShowSubtleErrorNotification).toHaveBeenCalledOnce()
    expect(mockShowSubtleErrorNotification).toHaveBeenCalledWith(
      'AutoResearch',
      'network timeout',
      'warning',
    )
  })

  it('fetchStats sets error ref and shows notification on failure', async () => {
    mockGet.mockRejectedValue(new Error('stats unavailable'))

    const { error, fetchStats } = useAutoResearch()
    await fetchStats()

    expect(error.value).toBe('stats unavailable')
    expect(mockShowSubtleErrorNotification).toHaveBeenCalledOnce()
    expect(mockShowSubtleErrorNotification).toHaveBeenCalledWith(
      'AutoResearch',
      'stats unavailable',
      'warning',
    )
  })

  it('fetchExperiments resets loading to false after failure', async () => {
    mockGet.mockRejectedValue(new Error('err'))

    const { loading, fetchExperiments } = useAutoResearch()
    await fetchExperiments()

    expect(loading.value).toBe(false)
  })

  it('fetchExperiments resets loading to false on success', async () => {
    mockGet.mockResolvedValue({ experiments: [] })

    const { loading, fetchExperiments } = useAutoResearch()
    await fetchExperiments()

    expect(loading.value).toBe(false)
  })
})
