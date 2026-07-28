// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Coverage for #12386 — the #12376 repoint of useBatchProcessingApi.toggleSchedule.
 *
 * PR #12376 corrected the prefix to /api/batch-jobs/schedules/{id} and issues a
 * PATCH with body `{ enabled }`. The backend route is still missing (tracked in
 * #12380), so these tests assert the *intended* request shape the method sends,
 * not a live round-trip.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useBatchProcessingApi } from '../useBatchProcessing'

const mockPatch = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: mockPatch
  })
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() })
}))

vi.mock('@/utils/cacheManagement', () => ({
  showSubtleErrorNotification: vi.fn()
}))

describe('useBatchProcessingApi.toggleSchedule (#12386)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('PATCHes /api/batch-jobs/schedules/{id} with { enabled: true }', async () => {
    mockPatch.mockResolvedValue({ id: 'sched-1', enabled: true })
    const { toggleSchedule } = useBatchProcessingApi()

    await toggleSchedule('sched-1', true)

    expect(mockPatch).toHaveBeenCalledWith('/api/batch-jobs/schedules/sched-1', {
      enabled: true
    })
  })

  it('forwards enabled=false in the PATCH body', async () => {
    mockPatch.mockResolvedValue({ id: 'sched-2', enabled: false })
    const { toggleSchedule } = useBatchProcessingApi()

    await toggleSchedule('sched-2', false)

    expect(mockPatch).toHaveBeenCalledWith('/api/batch-jobs/schedules/sched-2', {
      enabled: false
    })
  })

  it('returns null and does not throw when the PATCH rejects (route missing, #12380)', async () => {
    mockPatch.mockRejectedValue(new Error('405 Method Not Allowed'))
    const { toggleSchedule } = useBatchProcessingApi()

    const result = await toggleSchedule('sched-3', true)

    expect(result).toBeNull()
  })
})
