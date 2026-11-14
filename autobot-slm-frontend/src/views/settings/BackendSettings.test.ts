// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — BackendSettings' "Test connection" probe.
 *
 * `probeBackendHealth` uses the client's `rawRequest` with `keepSessionOn401`, so a
 * 4xx/5xx resolves with its status instead of throwing (and does not end the session).
 * These tests pin that a 401 backend reports "failed" (reachable, not authorised)
 * rather than erroring.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { backendClient } from '@/testing/mockAutobotBackendClient'
import BackendSettings from './BackendSettings.vue'
import en from '@/locales/en.json'

vi.mock('@/utils/slmSettingsApi', () => ({
  listSettings: vi.fn(async () => []),
  upsertSetting: vi.fn(async () => true),
}))

vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

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
    backendClient.rawRequest.mockReset()
    backendClient.rawRequest.mockResolvedValue({ ok: true, status: 200 })
  })

  it('probes /health through the shared client and reports connected', async () => {
    const vm = mountView()
    await flushPromises()
    backendClient.rawRequest.mockClear()

    await vm.testConnection()

    expect(backendClient.rawRequest.mock.calls[0][0]).toBe('/health')
    expect(vm.connectionStatus).toBe('connected')
    expect(vm.responseTime).not.toBeNull()
  })

  it('reports failed on a 401', async () => {
    backendClient.rawRequest.mockResolvedValue({ ok: false, status: 401 })

    const vm = mountView()
    await flushPromises()
    await vm.testConnection()

    expect(vm.connectionStatus).toBe('failed')
  })

  it('reports failed when the backend is unreachable', async () => {
    backendClient.rawRequest.mockRejectedValue(new Error('Network Error'))

    const vm = mountView()
    await flushPromises()
    await vm.testConnection()

    expect(vm.connectionStatus).toBe('failed')
  })
})
