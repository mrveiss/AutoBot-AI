// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — BackendSettings' "Test connection" probe.
 *
 * The probe was the one raw `fetch` here that was deliberately
 * unauthenticated, so converting it needed care: routing a diagnostic through
 * a client whose response interceptor clears `autobot_access_token` on a 401
 * would let "check whether the backend is up" log the operator out.
 *
 * `probeBackendHealth` therefore passes `validateStatus: () => true`, so the
 * request never rejects and the interceptor is never reached. These tests pin
 * that: a 401 backend reports "failed" (not reachable-and-authorised) while
 * the token in localStorage survives.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import axios from 'axios'
import BackendSettings from './BackendSettings.vue'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token', getApiUrl: () => 'https://slm.example' }),
}))

vi.mock('@/utils/slmSettingsApi', () => ({
  listSettings: vi.fn(async () => []),
  upsertSetting: vi.fn(async () => true),
}))

vi.mock('axios', () => {
  // The real response interceptor is registered here so the probe can be shown
  // NOT to trip it: `validateStatus` keeps a 401 on the success path.
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: () => undefined },
      response: {
        use: (_ok: unknown, onError: (e: unknown) => Promise<unknown>) => {
          ;(instance as unknown as { onError?: unknown }).onError = onError
        },
      },
    },
  }
  return { default: { create: () => instance } }
})

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

type MockedClient = {
  get: ReturnType<typeof vi.fn>
  onError?: (e: unknown) => Promise<unknown>
}

function client(): MockedClient {
  return (axios.create as unknown as () => MockedClient)()
}

type Vm = {
  connectionStatus: 'unknown' | 'connected' | 'failed'
  responseTime: number | null
  testConnection: () => Promise<void>
}

function mountView(): Vm {
  return mount(BackendSettings, { global: { plugins: [i18n] } }).vm as unknown as Vm
}

describe('BackendSettings connection probe (#13079)', () => {
  beforeEach(() => {
    localStorage.clear()
    const c = client()
    c.get.mockReset()
    c.get.mockResolvedValue({ data: { status: 'ok' }, status: 200 })
  })

  it('probes GET /health through the shared client and reports connected', async () => {
    const vm = mountView()
    await flushPromises()
    client().get.mockClear()

    await vm.testConnection()

    expect(client().get.mock.calls[0][0]).toBe('/health')
    expect(vm.connectionStatus).toBe('connected')
    expect(vm.responseTime).not.toBeNull()
  })

  it('reports failed on a 401 without clearing the autobot token', async () => {
    localStorage.setItem('autobot_access_token', 'autobot-token')
    client().get.mockResolvedValue({ data: {}, status: 401 })

    const vm = mountView()
    await flushPromises()
    await vm.testConnection()

    expect(vm.connectionStatus).toBe('failed')
    // The probe resolved, so the 401 interceptor never ran: an operator
    // diagnosing a backend outage does not get logged out as a side effect.
    expect(localStorage.getItem('autobot_access_token')).toBe('autobot-token')
  })

  it('reports failed when the backend is unreachable', async () => {
    client().get.mockRejectedValue(new Error('Network Error'))

    const vm = mountView()
    await flushPromises()
    await vm.testConnection()

    expect(vm.connectionStatus).toBe('failed')
  })
})
