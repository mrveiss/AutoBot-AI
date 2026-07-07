// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * Tests for useProbeBackedHealth composable (#7247).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

import { useProbeBackedHealth } from '../useProbeBackedHealth'
import { _resetProbeRegistryForTesting } from '../useHealthProbeRegistry'

// ---------------------------------------------------------------------------
// Module-level mock — useApiClient() returns a singleton, not Vue-injected
// ---------------------------------------------------------------------------

const fetchSpy = vi.fn()
const apiGetSpy = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: apiGetSpy, post: vi.fn(), put: vi.fn(), delete: vi.fn() }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

// ---------------------------------------------------------------------------
// Test types
// ---------------------------------------------------------------------------

interface TestHealthResponse {
  status: 'healthy' | 'unavailable'
  active_jobs: number
  redis_connected: boolean
  message?: string
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
  // Stub global fetch for the registry composable (fetches probe name list)
  vi.stubGlobal('fetch', fetchSpy)
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
      probes: [
        {
          name: 'batch_jobs',
          status: 'ok',
          data: { redis_connected: true },
          detail: 'all good',
        },
      ],
    })

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy,
      buildUnavailable,
      errorMessage: 'failed',
    })

    const result = await getHealth()
    expect(result).toEqual({
      status: 'healthy',
      active_jobs: 0,
      redis_connected: true,
      message: 'all good',
    })
  })

  it('returns buildUnavailable when probe is not in payload', async () => {
    apiGetSpy.mockResolvedValue({ probes: [] })

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy,
      buildUnavailable,
    })

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
      probes: [
        {
          name: 'batch_jobs',
          status: 'degraded',
          detail: 'redis is slow',
        },
      ],
    })

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy,
      buildUnavailable,
    })

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
      probes: [{ name: 'batch_jobs', status: 'unavailable' }],
    })

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy,
      buildUnavailable,
    })

    const result = await getHealth()
    expect(result?.message).toBe('Service unavailable')
  })

  it('returns buildUnavailable("Service unavailable") on fetch error', async () => {
    apiGetSpy.mockRejectedValue(new Error('network down'))

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy,
      buildUnavailable,
    })

    const result = await getHealth()
    expect(result?.status).toBe('unavailable')
    expect(result?.message).toBe('Service unavailable')
  })

  it('uses default errorMessage when none provided', async () => {
    apiGetSpy.mockRejectedValue(new Error('boom'))

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy,
      buildUnavailable,
    })

    const result = await getHealth()
    expect(result?.status).toBe('unavailable')
  })
})

describe('useProbeBackedHealth — renderNonOkFromProbe option', () => {
  it('calls buildHealthy (not buildUnavailable) for a degraded probe when renderNonOkFromProbe is true', async () => {
    apiGetSpy.mockResolvedValue({
      probes: [
        {
          name: 'batch_jobs',
          status: 'degraded',
          data: { redis_connected: false },
          detail: 'redis is slow',
        },
      ],
    })

    const buildHealthySpy = vi.fn(buildHealthy)
    const buildUnavailableSpy = vi.fn(buildUnavailable)

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy: buildHealthySpy,
      buildUnavailable: buildUnavailableSpy,
      renderNonOkFromProbe: true,
    })

    const result = await getHealth()
    expect(buildHealthySpy).toHaveBeenCalledOnce()
    expect(buildUnavailableSpy).not.toHaveBeenCalled()
    expect(result?.status).toBe('healthy')
    expect(result?.message).toBe('redis is slow')
  })

  it('still calls buildUnavailable for a missing probe even when renderNonOkFromProbe is true', async () => {
    apiGetSpy.mockResolvedValue({ probes: [] })

    const buildHealthySpy = vi.fn(buildHealthy)
    const buildUnavailableSpy = vi.fn(buildUnavailable)

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy: buildHealthySpy,
      buildUnavailable: buildUnavailableSpy,
      renderNonOkFromProbe: true,
    })

    const result = await getHealth()
    expect(buildUnavailableSpy).toHaveBeenCalledOnce()
    expect(buildHealthySpy).not.toHaveBeenCalled()
    expect(result?.status).toBe('unavailable')
    expect(result?.message).toBe('batch_jobs probe not registered')
  })

  it('default behavior (renderNonOkFromProbe absent) still routes degraded → buildUnavailable', async () => {
    apiGetSpy.mockResolvedValue({
      probes: [
        {
          name: 'batch_jobs',
          status: 'degraded',
          detail: 'degraded detail',
        },
      ],
    })

    const buildHealthySpy = vi.fn(buildHealthy)
    const buildUnavailableSpy = vi.fn(buildUnavailable)

    const getHealth = useProbeBackedHealth<TestHealthResponse>({
      probeName: 'batch_jobs',
      buildHealthy: buildHealthySpy,
      buildUnavailable: buildUnavailableSpy,
      // renderNonOkFromProbe not set → legacy behavior
    })

    const result = await getHealth()
    expect(buildUnavailableSpy).toHaveBeenCalledOnce()
    expect(buildHealthySpy).not.toHaveBeenCalled()
    expect(result?.status).toBe('unavailable')
    expect(result?.message).toBe('degraded detail')
  })
})
