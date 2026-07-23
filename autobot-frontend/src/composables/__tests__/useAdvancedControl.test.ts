// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Unit tests for useAdvancedControl (#12162, #12102, #11506 T1 — Stage 1).
 *
 * Covers: loadTakeovers populates pending/active/status from the client,
 * approve/pause/resume/complete call the right client methods and refresh
 * state on success, and failures (success:false or thrown) surface via the
 * `error` ref without throwing.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { effectScope } from 'vue'

const mockGetPendingTakeovers = vi.fn()
const mockGetActiveTakeovers = vi.fn()
const mockGetTakeoverStatus = vi.fn()
const mockApproveTakeover = vi.fn()
const mockPauseTakeoverSession = vi.fn()
const mockResumeTakeoverSession = vi.fn()
const mockCompleteTakeoverSession = vi.fn()
const mockExecuteTakeoverAction = vi.fn()

vi.mock('@/utils/AdvancedControlApiClient', () => ({
  advancedControlApiClient: {
    getPendingTakeovers: (...args: unknown[]) => mockGetPendingTakeovers(...args),
    getActiveTakeovers: (...args: unknown[]) => mockGetActiveTakeovers(...args),
    getTakeoverStatus: (...args: unknown[]) => mockGetTakeoverStatus(...args),
    approveTakeover: (...args: unknown[]) => mockApproveTakeover(...args),
    pauseTakeoverSession: (...args: unknown[]) => mockPauseTakeoverSession(...args),
    resumeTakeoverSession: (...args: unknown[]) => mockResumeTakeoverSession(...args),
    completeTakeoverSession: (...args: unknown[]) => mockCompleteTakeoverSession(...args),
    executeTakeoverAction: (...args: unknown[]) => mockExecuteTakeoverAction(...args),
  },
}))

import { useAdvancedControl } from '../useAdvancedControl'
import { useUserStore } from '@/stores/useUserStore'

const okEmpty = { success: true, data: { pending_requests: [], count: 0 } }
const okEmptyActive = { success: true, data: { active_sessions: [], count: 0 } }
const okStatus = {
  success: true,
  data: {
    pending_requests_count: 0,
    active_sessions_count: 0,
    paused_tasks_count: 0,
    total_completed_sessions: 0,
    system_status: 'normal' as const,
  },
}

function resetMocks(): void {
  mockGetPendingTakeovers.mockReset().mockResolvedValue(okEmpty)
  mockGetActiveTakeovers.mockReset().mockResolvedValue(okEmptyActive)
  mockGetTakeoverStatus.mockReset().mockResolvedValue(okStatus)
  mockApproveTakeover.mockReset()
  mockPauseTakeoverSession.mockReset()
  mockResumeTakeoverSession.mockReset()
  mockCompleteTakeoverSession.mockReset()
  mockExecuteTakeoverAction.mockReset()
}

describe('useAdvancedControl', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('starts with empty state', () => {
    const { pendingTakeovers, activeTakeovers, takeoverStatus, loading, error } = useAdvancedControl()
    expect(pendingTakeovers.value).toEqual([])
    expect(activeTakeovers.value).toEqual([])
    expect(takeoverStatus.value).toBeNull()
    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
  })

  it('loadTakeovers populates pending/active/status from the client', async () => {
    const pendingReq = {
      request_id: 'r1',
      trigger: 'MANUAL_REQUEST' as const,
      reason: 'needs a human',
      requesting_agent: 'agent-1',
      affected_tasks: [],
      priority: 'HIGH' as const,
      created_at: '2026-07-23T00:00:00Z',
      timeout_at: null,
      auto_approve: false,
    }
    const activeSession = {
      session_id: 's1',
      request_id: 'r1',
      human_operator: 'alice',
      status: 'active' as const,
      started_at: '2026-07-23T00:00:00Z',
      paused_at: null,
      actions_executed: 2,
      takeover_scope: {},
    }
    mockGetPendingTakeovers.mockResolvedValueOnce({ success: true, data: { pending_requests: [pendingReq], count: 1 } })
    mockGetActiveTakeovers.mockResolvedValueOnce({ success: true, data: { active_sessions: [activeSession], count: 1 } })
    mockGetTakeoverStatus.mockResolvedValueOnce({
      success: true,
      data: { pending_requests_count: 1, active_sessions_count: 1, paused_tasks_count: 0, total_completed_sessions: 5, system_status: 'takeover_active' },
    })

    const scope = effectScope()
    await scope.run(async () => {
      const { loadTakeovers, pendingTakeovers, activeTakeovers, takeoverStatus, loading, error } = useAdvancedControl()
      const promise = loadTakeovers()
      expect(loading.value).toBe(true)
      await promise

      expect(loading.value).toBe(false)
      expect(error.value).toBeNull()
      expect(pendingTakeovers.value).toEqual([pendingReq])
      expect(activeTakeovers.value).toEqual([activeSession])
      expect(takeoverStatus.value?.system_status).toBe('takeover_active')
    })
    scope.stop()
  })

  it('approve calls approveTakeover with the current username and reloads', async () => {
    const userStore = useUserStore()
    userStore.currentUser = { id: 'u1', username: 'alice' } as never
    mockApproveTakeover.mockResolvedValueOnce({ success: true, data: { success: true, session_id: 's1' } })

    const scope = effectScope()
    await scope.run(async () => {
      const { approve } = useAdvancedControl()
      const result = await approve('r1')
      expect(result).toBe(true)
    })
    scope.stop()

    expect(mockApproveTakeover).toHaveBeenCalledWith('r1', { human_operator: 'alice' })
    expect(mockGetPendingTakeovers).toHaveBeenCalled()
  })

  it('pause/resume/complete call the matching client methods and reload on success', async () => {
    mockPauseTakeoverSession.mockResolvedValueOnce({ success: true, data: { success: true, session_id: 's1', status: 'paused' } })
    mockResumeTakeoverSession.mockResolvedValueOnce({ success: true, data: { success: true, session_id: 's1', status: 'active' } })
    mockCompleteTakeoverSession.mockResolvedValueOnce({ success: true, data: { success: true, session_id: 's1', status: 'completed' } })

    const scope = effectScope()
    await scope.run(async () => {
      const { pause, resume, complete } = useAdvancedControl()
      expect(await pause('s1')).toBe(true)
      expect(await resume('s1')).toBe(true)
      expect(await complete('s1')).toBe(true)
    })
    scope.stop()

    expect(mockPauseTakeoverSession).toHaveBeenCalledWith('s1')
    expect(mockResumeTakeoverSession).toHaveBeenCalledWith('s1')
    expect(mockCompleteTakeoverSession).toHaveBeenCalledWith('s1', {})
  })

  it('surfaces a client success:false error without throwing', async () => {
    mockApproveTakeover.mockResolvedValueOnce({ success: false, error: 'already approved' })

    const scope = effectScope()
    await scope.run(async () => {
      const { approve, error } = useAdvancedControl()
      const result = await approve('r1')
      expect(result).toBe(false)
      expect(error.value).toBe('already approved')
    })
    scope.stop()
  })

  it('surfaces a thrown error (network failure) via the error ref', async () => {
    mockGetPendingTakeovers.mockRejectedValueOnce(new Error('network down'))
    mockGetActiveTakeovers.mockRejectedValueOnce(new Error('network down'))
    mockGetTakeoverStatus.mockRejectedValueOnce(new Error('network down'))

    const scope = effectScope()
    await scope.run(async () => {
      const { loadTakeovers, error } = useAdvancedControl()
      await loadTakeovers()
      expect(error.value).toBe('network down')
    })
    scope.stop()
  })
})
