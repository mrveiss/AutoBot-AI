// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #13079 — RedisServicePanel reaches the autobot backend through
 * `useAutobotApi` instead of a private `fetch` that sent only
 * `Bearer ${authStore.token}` (no `autobot_access_token` fallback, no 401
 * cleanup, and — for a panel that polls every 10s — no timeout at all).
 *
 * `useAutobotApi` adds a 30s timeout but performs no retries, so a slow
 * backend cannot stack retry attempts inside the 10s poll interval; the test
 * below pins the poll cadence to one request per tick.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import axios from 'axios'
import RedisServicePanel from './RedisServicePanel.vue'
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

const STATUS = {
  status: 'running' as const,
  uptime_seconds: 3600,
  memory_used_bytes: 1048576,
  memory_peak_bytes: 2097152,
  connected_clients: 4,
  last_checked: '2026-01-01T00:00:00Z',
}

type Vm = {
  redisStatus: typeof STATUS | null
  errorMessage: string | null
  performAction: (action: 'start' | 'stop' | 'restart') => Promise<void>
}

function mountPanel(): Vm {
  return mount(RedisServicePanel, { global: { plugins: [i18n] } }).vm as unknown as Vm
}

describe('RedisServicePanel transport (#13079)', () => {
  beforeEach(() => {
    const c = client()
    c.get.mockReset()
    c.post.mockReset()
    c.get.mockResolvedValue({ data: STATUS, status: 200 })
    c.post.mockResolvedValue({ data: { success: true }, status: 200 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('GETs /redis-service/status on mount and stores the payload', async () => {
    const vm = mountPanel()
    await flushPromises()

    expect(client().get.mock.calls[0][0]).toBe('/redis-service/status')
    expect(vm.redisStatus).toEqual(STATUS)
  })

  it('POSTs /redis-service/{action} and refreshes the status once', async () => {
    const vm = mountPanel()
    await flushPromises()
    client().get.mockClear()

    await vm.performAction('restart')
    await flushPromises()

    expect(client().post.mock.calls[0][0]).toBe('/redis-service/restart')
    expect(client().get.mock.calls.map((c) => c[0])).toEqual(['/redis-service/status'])
  })

  it('surfaces the backend detail when an action is refused', async () => {
    const vm = mountPanel()
    await flushPromises()
    client().post.mockRejectedValue({ response: { data: { detail: 'redis unit is masked' } } })

    await vm.performAction('stop')
    await flushPromises()

    expect(vm.errorMessage).toBe('redis unit is masked')
  })

  it('issues exactly one status request per 10s poll tick (no stacked retries)', async () => {
    vi.useFakeTimers()
    mountPanel()
    await flushPromises()
    client().get.mockClear()

    await vi.advanceTimersByTimeAsync(30_000)

    expect(client().get.mock.calls.map((c) => c[0])).toEqual([
      '/redis-service/status',
      '/redis-service/status',
      '/redis-service/status',
    ])
  })
})
