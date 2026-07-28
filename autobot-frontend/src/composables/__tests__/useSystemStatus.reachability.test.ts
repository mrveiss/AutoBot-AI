// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#12866: the two service-monitor probes carry a 5s budget, but the backend
// stalls in bursts (a CPU-bound scan holds the GIL and blocks the event loop for
// 12s+). Measured: 27.5% of polls exceeded the budget while /api/health kept
// returning 200 and the process never restarted — so a healthy backend was
// reported "Unreachable" about a quarter of the time.
//
// A failed status probe must therefore be confirmed against /api/health before
// declaring the backend down.

import { beforeEach, describe, expect, it, vi } from 'vitest'

const fetchWithFallback = vi.fn()

vi.mock('@/utils/ApiEndpointMapper.js', () => ({
  default: { fetchWithFallback: (...a: unknown[]) => fetchWithFallback(...a) },
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/composables/usePollingJob', () => ({
  usePollingJob: () => ({ start: vi.fn(), stop: vi.fn() }),
}))

import { useSystemStatus } from '../useSystemStatus'

const STALLED = new Error('timeout of 5000ms exceeded')

function healthOk() {
  return { ok: true, status: 200, fallback: false, json: async () => ({ status: 'ok' }), text: async () => 'ok' }
}

describe('useSystemStatus backend reachability (GH#12866)', () => {
  beforeEach(() => {
    fetchWithFallback.mockReset()
  })

  it('reports Degraded, not Unreachable, when status probes time out but health responds', async () => {
    fetchWithFallback.mockImplementation((url: string) => {
      if (url.includes('/health')) return Promise.resolve(healthOk())
      return Promise.reject(STALLED)
    })

    const { refreshSystemStatus, systemServices, systemStatus } = useSystemStatus()
    await refreshSystemStatus()

    const backend = systemServices.value.find((s) => s.name === 'Backend API')
    expect(backend?.statusText).toContain('Degraded')
    expect(backend?.statusText).not.toContain('Unreachable')
    expect(systemStatus.value.backendUnreachable).toBe(false)
  })

  it('still reports Unreachable when health fails too', async () => {
    fetchWithFallback.mockRejectedValue(STALLED)

    const { refreshSystemStatus, systemServices, systemStatus } = useSystemStatus()
    await refreshSystemStatus()

    const backend = systemServices.value.find((s) => s.name === 'Backend API')
    expect(backend?.statusText).toContain('Unreachable')
    expect(systemStatus.value.backendUnreachable).toBe(true)
  })

  it('does not probe health when the status endpoints succeed', async () => {
    fetchWithFallback.mockResolvedValue({
      ok: true,
      status: 200,
      fallback: false,
      json: async () => ({ vms: [], services: [] }),
      text: async () => '',
    })

    const { refreshSystemStatus } = useSystemStatus()
    await refreshSystemStatus()

    const healthCalls = fetchWithFallback.mock.calls.filter((c) => String(c[0]).includes('/health'))
    expect(healthCalls).toHaveLength(0)
  })

  it('treats a fallback response as not reachable', async () => {
    // A fallback means the mapper served canned data, not the backend.
    fetchWithFallback.mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({ ok: true, status: 200, fallback: true, json: async () => ({}), text: async () => '' })
      }
      return Promise.reject(STALLED)
    })

    const { refreshSystemStatus, systemStatus } = useSystemStatus()
    await refreshSystemStatus()

    expect(systemStatus.value.backendUnreachable).toBe(true)
  })
})
