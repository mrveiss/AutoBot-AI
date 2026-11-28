// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — CacheSettings' Redis-database clear.
 *
 * The private `fetch` here never inspected `response.ok`, so a rejected clear
 * still reported "cleared successfully" to the operator. Routing it through
 * `useAutobotApi` also fixes that: the client rejects on a non-2xx, so the
 * banner now reflects the real outcome. That is a deliberate behaviour change
 * and is pinned below alongside the endpoint path.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import CacheSettings from './CacheSettings.vue'
import { HttpError } from '@autobot/ui'
import { backendClient } from '@/testing/mockAutobotBackendClient'
import en from '@/locales/en.json'

vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

type Vm = {
  error: string | null
  success: string | null
  clearRedisCache: (database: string) => Promise<void>
}

function mountView(): Vm {
  return mount(CacheSettings, { global: { plugins: [i18n] } }).vm as unknown as Vm
}

describe('CacheSettings Redis clear transport (#13079)', () => {
  beforeEach(() => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    backendClient.get.mockReset()
    backendClient.post.mockReset()
    backendClient.get.mockResolvedValue({})
    backendClient.post.mockResolvedValue({ cleared: 12 })
  })

  it('POSTs /cache/redis/clear/{database} through the shared client', async () => {
    const vm = mountView()
    await flushPromises()
    backendClient.post.mockClear()

    await vm.clearRedisCache('sessions')

    expect(backendClient.post.mock.calls[0][0]).toBe('/cache/redis/clear/sessions')
    expect(vm.success).toContain('sessions')
    expect(vm.error).toBeNull()
  })

  it('reports the failure instead of a false success when the clear is refused', async () => {
    const vm = mountView()
    await flushPromises()
    backendClient.post.mockRejectedValue(new HttpError(403, 'Forbidden', { detail: 'database is protected' }))

    await vm.clearRedisCache('sessions')

    expect(vm.error).toBe('database is protected')
    expect(vm.success).toBeNull()
  })

  it('makes no request when the operator cancels the confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const vm = mountView()
    await flushPromises()
    backendClient.post.mockClear()

    await vm.clearRedisCache('sessions')

    expect(backendClient.post).not.toHaveBeenCalled()
  })
})
