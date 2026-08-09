// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#12866: a stalled status probe told the user nothing true.
//
// The panel replaced its eight service rows with three placeholders and the
// text "Backend API — Unreachable", so a backend that was healthy and merely
// GIL-starved for 12s presented as a fleet outage: Redis, Ollama, the NPU
// worker and the AI stack all vanished from the list, and the one row left
// asserted unreachability on a single-box deployment with no network to be
// unreachable across.
//
// What the probe failure actually establishes is that the CURRENT state is
// unknown. The last observed state is still the best information available, so
// it is shown, stamped, and marked stale — never dropped, and never re-asserted
// as live.

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

const STALLED = new Error('timeout of 12000ms exceeded')

function jsonOk(body: unknown) {
  return { ok: true, status: 200, fallback: false, json: async () => body, text: async () => '' }
}

/** A healthy poll: two VMs from /vms/status, two services from /services. */
function healthyFleet(url: string) {
  if (url.includes('/vms/status')) {
    return Promise.resolve(
      jsonOk({
        vms: [
          { name: 'AI Stack (ChromaDB)', status: 'online', message: 'Running' },
          { name: 'NPU Worker', status: 'online', message: 'Running' },
        ],
      }),
    )
  }
  if (url.includes('/services')) {
    return Promise.resolve(
      jsonOk({ services: { redis: { status: 'healthy', health: 'Connected' } } }),
    )
  }
  return Promise.resolve(jsonOk({ status: 'ok' }))
}

describe('useSystemStatus stale-state presentation (GH#12866)', () => {
  beforeEach(() => {
    fetchWithFallback.mockReset()
  })

  it('keeps the last observed services when a later poll stalls', async () => {
    fetchWithFallback.mockImplementation((url: string) => healthyFleet(url))
    const { refreshSystemStatus, systemServices } = useSystemStatus()
    await refreshSystemStatus()

    expect(systemServices.value.map((s) => s.name)).toEqual(
      expect.arrayContaining(['AI Stack (ChromaDB)', 'NPU Worker', 'Redis']),
    )

    // Now the backend stalls: status probes time out, /api/health still answers.
    fetchWithFallback.mockImplementation((url: string) =>
      url.includes('/health') ? Promise.resolve(jsonOk({ status: 'ok' })) : Promise.reject(STALLED),
    )
    await refreshSystemStatus()

    const names = systemServices.value.map((s) => s.name)
    expect(names).toEqual(expect.arrayContaining(['AI Stack (ChromaDB)', 'NPU Worker', 'Redis']))
  })

  it('marks the retained rows as last-known rather than re-asserting them as live', async () => {
    fetchWithFallback.mockImplementation((url: string) => healthyFleet(url))
    const { refreshSystemStatus, systemServices } = useSystemStatus()
    await refreshSystemStatus()

    fetchWithFallback.mockImplementation((url: string) =>
      url.includes('/health') ? Promise.resolve(jsonOk({ status: 'ok' })) : Promise.reject(STALLED),
    )
    await refreshSystemStatus()

    const redis = systemServices.value.find((s) => s.name === 'Redis')
    expect(redis?.statusText).toContain('last known')
    // A green row from a previous poll must not read as a live green row.
    expect(redis?.status).toBe('warning')
  })

  it('stamps the Backend API row with when the shown status was observed', async () => {
    fetchWithFallback.mockImplementation((url: string) => healthyFleet(url))
    const { refreshSystemStatus, systemServices } = useSystemStatus()
    await refreshSystemStatus()

    fetchWithFallback.mockImplementation((url: string) =>
      url.includes('/health') ? Promise.resolve(jsonOk({ status: 'ok' })) : Promise.reject(STALLED),
    )
    await refreshSystemStatus()

    const backend = systemServices.value.find((s) => s.name === 'Backend API')
    expect(backend?.statusText).toContain('Degraded')
    expect(backend?.statusText).toMatch(/status as of \d{1,2}[:.]\d{2}/)
  })

  it('omits the stamp on a first-ever poll, having observed nothing to stamp', async () => {
    fetchWithFallback.mockImplementation((url: string) =>
      url.includes('/health') ? Promise.resolve(jsonOk({ status: 'ok' })) : Promise.reject(STALLED),
    )
    const { refreshSystemStatus, systemServices } = useSystemStatus()
    await refreshSystemStatus()

    const backend = systemServices.value.find((s) => s.name === 'Backend API')
    expect(backend?.statusText).toContain('Degraded')
    expect(backend?.statusText).not.toContain('status as of')
  })

  it('does not resurrect a stale snapshot as if it were current once polls recover', async () => {
    fetchWithFallback.mockImplementation((url: string) => healthyFleet(url))
    const { refreshSystemStatus, systemServices } = useSystemStatus()
    await refreshSystemStatus()

    fetchWithFallback.mockImplementation((url: string) =>
      url.includes('/health') ? Promise.resolve(jsonOk({ status: 'ok' })) : Promise.reject(STALLED),
    )
    await refreshSystemStatus()

    fetchWithFallback.mockImplementation((url: string) => healthyFleet(url))
    await refreshSystemStatus()

    const redis = systemServices.value.find((s) => s.name === 'Redis')
    expect(redis?.statusText).not.toContain('last known')
    expect(redis?.status).toBe('healthy')
  })
})
