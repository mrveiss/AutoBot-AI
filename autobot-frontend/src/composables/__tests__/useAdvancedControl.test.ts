// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Unit tests for useAdvancedControl (#12162, #12102, #11506 T1 — Stage 1;
 * #12169, #12102 — Stage 2 streaming sessions).
 *
 * Covers: loadTakeovers populates pending/active/status from the client,
 * approve/pause/resume/complete call the right client methods and refresh
 * state on success, failures (success:false or thrown) surface via the
 * `error` ref without throwing, and the Stage 2 streaming equivalents
 * (loadStreaming/createStreaming/terminateStreaming).
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
const mockListStreamingSessions = vi.fn()
const mockGetStreamingCapabilities = vi.fn()
const mockCreateStreamingSession = vi.fn()
const mockTerminateStreamingSession = vi.fn()

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
    listStreamingSessions: (...args: unknown[]) => mockListStreamingSessions(...args),
    getStreamingCapabilities: (...args: unknown[]) => mockGetStreamingCapabilities(...args),
    createStreamingSession: (...args: unknown[]) => mockCreateStreamingSession(...args),
    terminateStreamingSession: (...args: unknown[]) => mockTerminateStreamingSession(...args),
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

const okEmptySessions = { success: true, data: { sessions: [], count: 0 } }
const okCapabilities = {
  success: true,
  data: {
    vnc_available: true,
    novnc_available: true,
    max_sessions: 4,
    supported_resolutions: ['1920x1080'],
    supported_depths: [24],
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
  mockListStreamingSessions.mockReset().mockResolvedValue(okEmptySessions)
  mockGetStreamingCapabilities.mockReset().mockResolvedValue(okCapabilities)
  mockCreateStreamingSession.mockReset()
  mockTerminateStreamingSession.mockReset()
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
    const { pendingTakeovers, activeTakeovers, takeoverStatus, streamingSessions, streamingCapabilities, loading, error } =
      useAdvancedControl()
    expect(pendingTakeovers.value).toEqual([])
    expect(activeTakeovers.value).toEqual([])
    expect(takeoverStatus.value).toBeNull()
    expect(streamingSessions.value).toEqual([])
    expect(streamingCapabilities.value).toBeNull()
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

  it('loadStreaming populates streamingSessions and streamingCapabilities from the client', async () => {
    const session = {
      session_id: 's1',
      user_id: 'u1',
      vnc_port: 5901,
      novnc_port: 6901,
      display: ':1',
      created_at: '2026-07-23T00:00:00Z',
      status: 'active' as const,
    }
    mockListStreamingSessions.mockResolvedValueOnce({ success: true, data: { sessions: [session], count: 1 } })
    mockGetStreamingCapabilities.mockResolvedValueOnce({
      success: true,
      data: {
        vnc_available: true,
        novnc_available: false,
        max_sessions: 2,
        supported_resolutions: ['1280x720'],
        supported_depths: [16],
      },
    })

    const scope = effectScope()
    await scope.run(async () => {
      const { loadStreaming, streamingSessions, streamingCapabilities, loading, error } = useAdvancedControl()
      const promise = loadStreaming()
      expect(loading.value).toBe(true)
      await promise

      expect(loading.value).toBe(false)
      expect(error.value).toBeNull()
      expect(streamingSessions.value).toEqual([session])
      expect(streamingCapabilities.value?.max_sessions).toBe(2)
    })
    scope.stop()
  })

  it('createStreaming calls createStreamingSession with the request and reloads on success', async () => {
    mockCreateStreamingSession.mockResolvedValueOnce({
      success: true,
      data: {
        session_id: 's1',
        vnc_port: 5901,
        novnc_port: 6901,
        display: ':1',
        vnc_url: 'vnc://host:5901',
        web_url: 'http://host:6901',
        websocket_endpoint: '/ws/desktop/s1',
      },
    })

    const scope = effectScope()
    await scope.run(async () => {
      const { createStreaming } = useAdvancedControl()
      const result = await createStreaming({ user_id: 'u1', resolution: '1920x1080', depth: 24 })
      expect(result).toBe(true)
    })
    scope.stop()

    expect(mockCreateStreamingSession).toHaveBeenCalledWith({ user_id: 'u1', resolution: '1920x1080', depth: 24 })
    expect(mockListStreamingSessions).toHaveBeenCalled()
  })

  it('terminateStreaming calls terminateStreamingSession and reloads on success', async () => {
    mockTerminateStreamingSession.mockResolvedValueOnce({ success: true, data: { success: true, session_id: 's1' } })

    const scope = effectScope()
    await scope.run(async () => {
      const { terminateStreaming } = useAdvancedControl()
      const result = await terminateStreaming('s1')
      expect(result).toBe(true)
    })
    scope.stop()

    expect(mockTerminateStreamingSession).toHaveBeenCalledWith('s1')
    expect(mockListStreamingSessions).toHaveBeenCalled()
  })

  it('surfaces a createStreaming client success:false error without throwing', async () => {
    mockCreateStreamingSession.mockResolvedValueOnce({ success: false, error: 'max sessions reached' })

    const scope = effectScope()
    await scope.run(async () => {
      const { createStreaming, error } = useAdvancedControl()
      const result = await createStreaming({ user_id: 'u1' })
      expect(result).toBe(false)
      expect(error.value).toBe('max sessions reached')
    })
    scope.stop()
    expect(mockListStreamingSessions).not.toHaveBeenCalled()
  })

  it('surfaces a terminateStreaming thrown error via the error ref', async () => {
    mockTerminateStreamingSession.mockRejectedValueOnce(new Error('network down'))

    const scope = effectScope()
    await scope.run(async () => {
      const { terminateStreaming, error } = useAdvancedControl()
      const result = await terminateStreaming('s1')
      expect(result).toBe(false)
      expect(error.value).toBe('network down')
    })
    scope.stop()
  })
})
