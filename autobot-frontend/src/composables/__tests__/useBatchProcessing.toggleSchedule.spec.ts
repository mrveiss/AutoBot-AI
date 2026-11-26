// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Coverage for #12386 — useBatchProcessingApi.toggleSchedule.
 *
 * PATCH /api/batch-jobs/schedules/{id} with body `{ enabled }` (#12376, served since #12380).
 * Since #21649 the call goes through the typed `apiClient.call` and rejects on failure
 * instead of resolving null, so the caller can report it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockCall } = vi.hoisted(() => ({ mockCall: vi.fn() }))

vi.mock('@/utils/ApiClient', () => ({ default: { call: mockCall, post: vi.fn() } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))
vi.mock('@/composables/useProbeBackedHealth', () => ({
  useProbeBackedHealth: () => vi.fn(),
  probeStatusToLegacy: vi.fn(),
}))

import { useBatchProcessingApi } from '../useBatchProcessing'

describe('useBatchProcessingApi.toggleSchedule (#12386)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('PATCHes /api/batch-jobs/schedules/{id} with { enabled: true }', async () => {
    mockCall.mockResolvedValue({ schedule_id: 'sched-1', enabled: true })
    const { toggleSchedule } = useBatchProcessingApi()

    await toggleSchedule('sched-1', true)

    expect(mockCall).toHaveBeenCalledWith('patch', '/api/batch-jobs/schedules/{schedule_id}', {
      path: { schedule_id: 'sched-1' },
      body: { enabled: true },
    })
  })

  it('forwards enabled=false in the PATCH body', async () => {
    mockCall.mockResolvedValue({ schedule_id: 'sched-2', enabled: false })
    const { toggleSchedule } = useBatchProcessingApi()

    await toggleSchedule('sched-2', false)

    expect(mockCall).toHaveBeenCalledWith('patch', '/api/batch-jobs/schedules/{schedule_id}', {
      path: { schedule_id: 'sched-2' },
      body: { enabled: false },
    })
  })

  it('rejects with the backend error when the PATCH fails (#21649)', async () => {
    const failure = new Error('HTTP 404')
    mockCall.mockRejectedValue(failure)
    const { toggleSchedule } = useBatchProcessingApi()

    await expect(toggleSchedule('sched-3', true)).rejects.toBe(failure)
  })
})
