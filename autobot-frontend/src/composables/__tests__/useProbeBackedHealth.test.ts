/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * Tests for useProbeBackedHealth composable (#7247).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'

import { useProbeBackedHealth } from '../useProbeBackedHealth'
import { _resetProbeRegistryForTesting } from '../useHealthProbeRegistry'

// ---------------------------------------------------------------------------
// Test rig: minimal Vue app + apiClient provider
// ---------------------------------------------------------------------------

interface TestHealthResponse {
  status: 'healthy' | 'unavailable'
  active_jobs: number
  redis_connected: boolean
  message?: string
}

const fetchSpy = vi.fn()
const apiGetSpy = vi.fn()

function withApi<T>(setup: () => T): T {
  let result!: T
  const Wrapper = defineComponent({
    setup() {
      result = setup()
      return {}
    },
    template: '<div />',
  })
  mount(Wrapper, {
    global: {
      provide: {
        apiClient: {
          get: apiGetSpy,
          post: vi.fn(),
          put: vi.fn(),
          delete: vi.fn(),
        },
      },
    },
  })
  return result
}

function buildHealthy(probe: { detail?: string }, data: Record<string, unknown>): TestHealthResponse {
  return {
    status: 'healthy',
    active_jobs: 0,
    redis_connected: Boolean(data.redis_connected),
    message: probe.detail,
  }
}

function buildUnavailable(message: string): TestHealthResponse {
  return {
    status: 'unavailable',
    active_jobs: 0,
    redis_connected: false,
    message,
  }
}

beforeEach(() => {
  fetchSpy.mockReset()
  apiGetSpy.mockReset()
  _resetProbeRegistryForTesting()
  // Stub global fetch for the registry composable
  vi.stubGlobal('fetch', fetchSpy)
  // Default: registry returns the probe names we use in tests
  fetchSpy.mockResolvedValue({
    ok: true,
    json: async () => ['batch_jobs', 'long_running'],
  })
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useProbeBackedHealth', () => {
  it('returns buildHealthy result when probe found and status === ok', async () => {
    apiGetSpy.mockResolvedValue({
      json: async () => ({
        probes: [
          {
            name: 'batch_jobs',
            status: 'ok',
            data: { redis_connected: true },
            detail: 'all good',
          },
        ],
      }),
    })

    const getHealth = withApi(() =>
      useProbeBackedHealth<TestHealthResponse>({
        probeName: 'batch_jobs',
        buildHealthy,
        buildUnavailable,
        errorMessage: 'failed',
      })
    )

    const result = await getHealth()
    expect(result).toEqual({
      status: 'healthy',
      active_jobs: 0,
      redis_connected: true,
      message: 'all good',
    })
  })

  it('returns buildUnavailable when probe is not in payload', async () => {
    apiGetSpy.mockResolvedValue({
      json: async () => ({ probes: [] }),
    })

    const getHealth = withApi(() =>
      useProbeBackedHealth<TestHealthResponse>({
        probeName: 'batch_jobs',
        buildHealthy,
        buildUnavailable,
      })
    )

    const result = await getHealth()
    expect(result).toEqual({
      status: 'unavailable',
      active_jobs: 0,
      redis_connected: false,
      message: 'batch_jobs probe not registered',
    })
  })

  it('returns buildUnavailable with probe.detail when status is not ok', async () => {
    apiGetSpy.mockResolvedValue({
      json: async () => ({
        probes: [
          {
            name: 'batch_jobs',
            status: 'degraded',
            detail: 'redis is slow',
          },
        ],
      }),
    })

    const getHealth = withApi(() =>
      useProbeBackedHealth<TestHealthResponse>({
        probeName: 'batch_jobs',
        buildHealthy,
        buildUnavailable,
      })
    )

    const result = await getHealth()
    expect(result).toEqual({
      status: 'unavailable',
      active_jobs: 0,
      redis_connected: false,
      message: 'redis is slow',
    })
  })

  it('falls back to "Service unavailable" when status is not ok and no detail', async () => {
    apiGetSpy.mockResolvedValue({
      json: async () => ({
        probes: [{ name: 'batch_jobs', status: 'unavailable' }],
      }),
    })

    const getHealth = withApi(() =>
      useProbeBackedHealth<TestHealthResponse>({
        probeName: 'batch_jobs',
        buildHealthy,
        buildUnavailable,
      })
    )

    const result = await getHealth()
    expect(result?.message).toBe('Service unavailable')
  })

  it('returns buildUnavailable("Service unavailable") on fetch error', async () => {
    apiGetSpy.mockRejectedValue(new Error('network down'))

    const getHealth = withApi(() =>
      useProbeBackedHealth<TestHealthResponse>({
        probeName: 'batch_jobs',
        buildHealthy,
        buildUnavailable,
      })
    )

    const result = await getHealth()
    // withErrorHandling silent:true returns the fallbackValue on throw
    expect(result?.status).toBe('unavailable')
    expect(result?.message).toBe('Service unavailable')
  })

  it('uses default errorMessage when none provided', async () => {
    // The errorMessage default is `Failed to check ${probeName} service health`.
    // We can't directly observe it via the public API (it goes through
    // withErrorHandling's logging), but we verify the composable doesn't crash.
    apiGetSpy.mockRejectedValue(new Error('boom'))

    const getHealth = withApi(() =>
      useProbeBackedHealth<TestHealthResponse>({
        probeName: 'batch_jobs',
        buildHealthy,
        buildUnavailable,
      })
    )

    const result = await getHealth()
    expect(result?.status).toBe('unavailable')
  })
})
