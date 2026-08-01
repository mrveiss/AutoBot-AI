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
import axios from 'axios'
import CacheSettings from './CacheSettings.vue'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('axios', () => {
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: () => undefined },
      response: { use: () => undefined },
    },
  }
  return { default: { create: () => instance } }
})

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

type MockedClient = { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> }

function client(): MockedClient {
  return (axios.create as unknown as () => MockedClient)()
}

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
    const c = client()
    c.get.mockReset()
    c.post.mockReset()
    c.get.mockResolvedValue({ data: {}, status: 200 })
    c.post.mockResolvedValue({ data: { cleared: 12 }, status: 200 })
  })

  it('POSTs /cache/redis/clear/{database} through the shared client', async () => {
    const vm = mountView()
    await flushPromises()
    client().post.mockClear()

    await vm.clearRedisCache('sessions')

    expect(client().post.mock.calls[0][0]).toBe('/cache/redis/clear/sessions')
    expect(vm.success).toContain('sessions')
    expect(vm.error).toBeNull()
  })

  it('reports the failure instead of a false success when the clear is refused', async () => {
    const vm = mountView()
    await flushPromises()
    client().post.mockRejectedValue({ response: { data: { detail: 'database is protected' } } })

    await vm.clearRedisCache('sessions')

    expect(vm.error).toBe('database is protected')
    expect(vm.success).toBeNull()
  })

  it('makes no request when the operator cancels the confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const vm = mountView()
    await flushPromises()
    client().post.mockClear()

    await vm.clearRedisCache('sessions')

    expect(client().post).not.toHaveBeenCalled()
  })
})
