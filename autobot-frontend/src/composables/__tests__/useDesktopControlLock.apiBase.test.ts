// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #22144: the chat control lock reaches the backend through the canonical API base.
 * Through nginx a URL without it returns the SPA index.html (200 text/html), so this
 * drives the REAL ApiClient and asserts the URL fetch receives.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/utils/authToken', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/authToken')>()),
  readStoredAuthToken: () => 'live-jwt',
}))

import { getApiBase } from '@/config/ssot-config'
import { resetCircuitBreakers } from '@/utils/apiCircuitBreaker'
import { useDesktopControlLock } from '../useDesktopControlLock'

const lockState = { success: true, session_id: 'host-1', owner: null, human_active: false, message: 'ok' }

describe('useDesktopControlLock URL base', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  beforeEach(() => {
    setActivePinia(createPinia())
    resetCircuitBreakers()
    fetchMock = vi.fn(async () => new Response(JSON.stringify(lockState), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('status, acquire and release all start with getApiBase()', async () => {
    const { refreshStatus, takeControl, releaseControl } = useDesktopControlLock('host-1')
    await refreshStatus()
    await takeControl()
    await releaseControl()
    const urls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(urls).toHaveLength(3)
    const root = `${getApiBase()}/vnc-proxy/desktop/control/`
    expect(urls.every((u) => u.includes(root))).toBe(true)
    expect(urls[0]).toContain('/status?session_id=host-1')
    expect(urls[1]).toContain('/acquire')
    expect(urls[2]).toContain('/release')
  })
})
