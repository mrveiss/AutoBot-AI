// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit tests for useHealthProbeRegistry (#12363 Phase 2).
 *
 * Verifies the registry fetch was migrated off raw fetch() onto the
 * fetchWithAuth bridge (attaches the JWT), and that the graceful-null probe
 * semantics (non-ok / non-array / thrown error never poison the cache) are
 * preserved exactly.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

const fetchWithAuthSpy = vi.fn()

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthSpy(...args),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), warn: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))

import {
  getProbeRegistry,
  refreshProbeRegistry,
  findProbeByName,
  _resetProbeRegistryForTesting,
} from '../useHealthProbeRegistry'

beforeEach(() => {
  fetchWithAuthSpy.mockReset()
  _resetProbeRegistryForTesting()
})

describe('useHealthProbeRegistry — fetchWithAuth migration (#12363)', () => {
  it('routes the registry fetch through fetchWithAuth and returns a name Set', async () => {
    fetchWithAuthSpy.mockResolvedValue({ ok: true, json: async () => ['batch_jobs', 'long_running'] })

    const registry = await getProbeRegistry()

    expect(fetchWithAuthSpy).toHaveBeenCalledTimes(1)
    expect(fetchWithAuthSpy).toHaveBeenCalledWith('/api/system/health/probes')
    expect(registry).toEqual(new Set(['batch_jobs', 'long_running']))
  })

  it('caches after first fetch — a second call does not refetch', async () => {
    fetchWithAuthSpy.mockResolvedValue({ ok: true, json: async () => ['a'] })

    await getProbeRegistry()
    await getProbeRegistry()

    expect(fetchWithAuthSpy).toHaveBeenCalledTimes(1)
  })

  it('refreshProbeRegistry forces a refetch', async () => {
    fetchWithAuthSpy.mockResolvedValue({ ok: true, json: async () => ['a'] })

    await getProbeRegistry()
    await refreshProbeRegistry()

    expect(fetchWithAuthSpy).toHaveBeenCalledTimes(2)
  })

  it('returns null (does not poison cache) on a non-ok response', async () => {
    fetchWithAuthSpy.mockResolvedValue({ ok: false, status: 503 })
    expect(await getProbeRegistry()).toBeNull()

    // Next call retries rather than serving a poisoned cache.
    fetchWithAuthSpy.mockResolvedValue({ ok: true, json: async () => ['a'] })
    _resetProbeRegistryForTesting()
    expect(await getProbeRegistry()).toEqual(new Set(['a']))
  })

  it('returns null when the endpoint returns a non-string array', async () => {
    fetchWithAuthSpy.mockResolvedValue({ ok: true, json: async () => ({ not: 'an array' }) })
    expect(await getProbeRegistry()).toBeNull()
  })

  it('returns null when the fetch throws', async () => {
    fetchWithAuthSpy.mockRejectedValue(new Error('network down'))
    expect(await getProbeRegistry()).toBeNull()
  })

  it('findProbeByName returns the matching probe from the payload', async () => {
    fetchWithAuthSpy.mockResolvedValue({ ok: true, json: async () => ['known'] })
    const probes = [{ name: 'known', status: 'ok' as const }]
    expect(await findProbeByName(probes, 'known')).toEqual({ name: 'known', status: 'ok' })
  })
})
