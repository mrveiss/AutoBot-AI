// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Unit tests for useDesktopControlLock (#12002, #11506 T1).
 *
 * Covers: acquire (takeControl) / release call the correct endpoints,
 * isMine reflects the current user vs. lock owner, refreshStatus updates
 * state, and failures surface via the `error` ref without throwing.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { effectScope } from 'vue'

const mockGet = vi.fn(async (..._args: unknown[]) => ({}))
const mockPost = vi.fn(async (..._args: unknown[]) => ({}))

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args)
  }
}))

import { useDesktopControlLock } from '../useDesktopControlLock'
import { useUserStore } from '@/stores/useUserStore'
import { getApiBase } from '@/config/ssot-config'

function fakeState(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    success: true,
    session_id: 'host-1',
    owner: null,
    human_active: false,
    message: 'Agent has control',
    ...overrides
  }
}

describe('useDesktopControlLock', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockGet.mockReset()
    mockPost.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('builds every lock URL from the canonical API base (#22144)', async () => {
    mockGet.mockResolvedValueOnce(fakeState())
    mockPost.mockResolvedValue(fakeState({ owner: 'alice', human_active: true }))
    const { refreshStatus, takeControl, releaseControl } = useDesktopControlLock('host-1')
    await refreshStatus()
    await takeControl()
    await releaseControl()
    const urls = [mockGet.mock.calls[0][0], mockPost.mock.calls[0][0], mockPost.mock.calls[1][0]] as string[]
    expect(urls.every((u) => u.startsWith(`${getApiBase()}/vnc-proxy/desktop/control/`))).toBe(true)
  })

  it('makes no request without a selected host id (#22145)', async () => {
    const { refreshStatus, takeControl } = useDesktopControlLock('')
    expect(await refreshStatus()).toBeNull()
    expect(await takeControl()).toBeNull()
    expect(mockGet).not.toHaveBeenCalled()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('starts with no owner and human_active false', () => {
    const { owner, humanActive, isMine } = useDesktopControlLock('host-1')
    expect(owner.value).toBeNull()
    expect(humanActive.value).toBe(false)
    expect(isMine.value).toBe(false)
  })

  it('refreshStatus populates owner/humanActive from GET /control/status', async () => {
    mockGet.mockResolvedValueOnce(fakeState({ owner: 'alice', human_active: true }))

    const scope = effectScope()
    await scope.run(async () => {
      const { owner, humanActive, refreshStatus } = useDesktopControlLock('host-1')
      await refreshStatus()
      expect(owner.value).toBe('alice')
      expect(humanActive.value).toBe(true)
    })
    scope.stop()

    expect(mockGet).toHaveBeenCalledWith('/api/vnc-proxy/desktop/control/status?session_id=host-1')
  })

  it('takeControl calls POST /control/acquire and sets isMine when owner matches current user', async () => {
    const userStore = useUserStore()
    userStore.currentUser = {
      id: 'u1',
      username: 'alice',
      displayName: 'Alice',
      role: 'user',
      preferences: userStore.currentUser?.preferences as never,
      createdAt: new Date()
    } as never

    mockPost.mockResolvedValueOnce(fakeState({ owner: 'alice', human_active: true }))

    const scope = effectScope()
    await scope.run(async () => {
      const { takeControl, isMine, humanActive } = useDesktopControlLock('host-1')
      const result = await takeControl()

      expect(result?.success).toBe(true)
      expect(humanActive.value).toBe(true)
      expect(isMine.value).toBe(true)
    })
    scope.stop()

    expect(mockPost).toHaveBeenCalledWith('/api/vnc-proxy/desktop/control/acquire', { session_id: 'host-1' })
  })

  it('isMine is false when a different user holds the lock', async () => {
    const userStore = useUserStore()
    userStore.currentUser = { id: 'u1', username: 'alice' } as never

    mockPost.mockResolvedValueOnce(fakeState({ owner: 'bob', human_active: true }))

    const scope = effectScope()
    await scope.run(async () => {
      const { takeControl, isMine } = useDesktopControlLock('host-1')
      await takeControl()
      expect(isMine.value).toBe(false)
    })
    scope.stop()
  })

  it('releaseControl calls POST /control/release and clears owner', async () => {
    mockPost.mockResolvedValueOnce(fakeState())

    const scope = effectScope()
    await scope.run(async () => {
      const { releaseControl, owner, humanActive } = useDesktopControlLock('host-1')
      const result = await releaseControl()

      expect(result?.success).toBe(true)
      expect(owner.value).toBeNull()
      expect(humanActive.value).toBe(false)
    })
    scope.stop()

    expect(mockPost).toHaveBeenCalledWith('/api/vnc-proxy/desktop/control/release', { session_id: 'host-1' })
  })

  it('surfaces a denied release without throwing', async () => {
    mockPost.mockResolvedValueOnce(
      fakeState({ success: false, owner: 'alice', human_active: true, message: 'Control lock is held by another user' })
    )

    const scope = effectScope()
    await scope.run(async () => {
      const { releaseControl, error } = useDesktopControlLock('host-1')
      const result = await releaseControl()

      expect(result?.success).toBe(false)
      expect(error.value).toContain('held by another user')
    })
    scope.stop()
  })

  it('acquire failure (e.g. network error) sets error and does not throw', async () => {
    mockPost.mockRejectedValueOnce(new Error('network down'))

    const scope = effectScope()
    await scope.run(async () => {
      const { takeControl, error } = useDesktopControlLock('host-1')
      const result = await takeControl()

      expect(result).toBeNull()
      expect(error.value).toBe('network down')
    })
    scope.stop()
  })

  describe('heartbeat (#12002 review fixes)', () => {
    // Mirrors the composable's private HEARTBEAT_INTERVAL_MS.
    const HEARTBEAT_INTERVAL_MS = 30000

    beforeEach(() => {
      vi.useFakeTimers()
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    it('refreshStatus resumes the heartbeat when we already own the lock (remount)', async () => {
      const userStore = useUserStore()
      userStore.currentUser = { id: 'u1', username: 'alice' } as never

      mockGet.mockResolvedValueOnce(fakeState({ owner: 'alice', human_active: true }))
      mockPost.mockResolvedValue(fakeState({ owner: 'alice', human_active: true }))

      const scope = effectScope()
      await scope.run(async () => {
        const { refreshStatus } = useDesktopControlLock('host-1')
        await refreshStatus()

        expect(mockPost).not.toHaveBeenCalled()

        await vi.advanceTimersByTimeAsync(HEARTBEAT_INTERVAL_MS)

        expect(mockPost).toHaveBeenCalledWith('/api/vnc-proxy/desktop/control/acquire', { session_id: 'host-1' })
      })
      scope.stop()
    })

    it('refreshStatus does NOT start a heartbeat when a different user holds the lock', async () => {
      const userStore = useUserStore()
      userStore.currentUser = { id: 'u1', username: 'alice' } as never

      mockGet.mockResolvedValueOnce(fakeState({ owner: 'bob', human_active: true }))

      const scope = effectScope()
      await scope.run(async () => {
        const { refreshStatus } = useDesktopControlLock('host-1')
        await refreshStatus()

        await vi.advanceTimersByTimeAsync(HEARTBEAT_INTERVAL_MS * 2)
        expect(mockPost).not.toHaveBeenCalled()
      })
      scope.stop()
    })

    it('silent heartbeat re-acquire never toggles loading (no button flicker/disable)', async () => {
      const userStore = useUserStore()
      userStore.currentUser = { id: 'u1', username: 'alice' } as never

      mockGet.mockResolvedValueOnce(fakeState({ owner: 'alice', human_active: true }))

      let resolveHeartbeatPost: (value: unknown) => void = () => {}
      mockPost.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveHeartbeatPost = resolve
          })
      )

      const scope = effectScope()
      await scope.run(async () => {
        const { refreshStatus, loading } = useDesktopControlLock('host-1')
        await refreshStatus()

        await vi.advanceTimersByTimeAsync(HEARTBEAT_INTERVAL_MS)
        // Heartbeat POST is now in-flight (pending promise) -- loading must
        // stay false throughout (#12002 review nit).
        expect(loading.value).toBe(false)

        resolveHeartbeatPost(fakeState({ owner: 'alice', human_active: true }))
        await vi.advanceTimersByTimeAsync(0)
        expect(loading.value).toBe(false)
      })
      scope.stop()
    })

    it('scope disposal stops the resumed heartbeat', async () => {
      const userStore = useUserStore()
      userStore.currentUser = { id: 'u1', username: 'alice' } as never

      mockGet.mockResolvedValueOnce(fakeState({ owner: 'alice', human_active: true }))
      mockPost.mockResolvedValue(fakeState({ owner: 'alice', human_active: true }))

      const scope = effectScope()
      await scope.run(async () => {
        const { refreshStatus } = useDesktopControlLock('host-1')
        await refreshStatus()
      })
      scope.stop()

      await vi.advanceTimersByTimeAsync(HEARTBEAT_INTERVAL_MS * 3)
      expect(mockPost).not.toHaveBeenCalled()
    })

    it('takeControl still uses a non-silent acquire (loading toggles for the explicit user action)', async () => {
      mockPost.mockResolvedValueOnce(fakeState({ owner: 'alice', human_active: true }))

      const scope = effectScope()
      await scope.run(async () => {
        const { takeControl, loading } = useDesktopControlLock('host-1')
        const promise = takeControl()
        expect(loading.value).toBe(true)
        await promise
        expect(loading.value).toBe(false)
      })
      scope.stop()
    })
  })
})
