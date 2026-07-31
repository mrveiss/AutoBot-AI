// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * AlertsMonitor — the discarded DELETE response (#13140).
 *
 * "Clear all alerts" is the only DESTRUCTIVE action among this issue's 30
 * `getSlmApiBase()` sites, and it was the worst-handled: the call was written
 * `await fetch(url, { method: 'DELETE', headers })` with the Response never
 * bound to anything. A 401, a 403 or a 500 was therefore indistinguishable
 * from success — `refresh()` re-rendered the very same alerts and the operator,
 * who had just confirmed a "this cannot be undone" dialog, was left to infer
 * from an unchanged list that nothing had happened.
 *
 * The bearer was also built from `authStore.token`, a ref hydrated once at
 * store construction, so with a session only in storage the destructive call
 * went out anonymous.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import AlertsMonitor from './AlertsMonitor.vue'
import en from '@/locales/en.json'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))

const TOKEN_KEY = 'slm_access_token'

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const ALERTS = {
  total_count: 2,
  critical_count: 1,
  warning_count: 1,
  alerts: [
    { category: 'cpu', severity: 'critical', message: 'cpu hot', timestamp: '2026-01-01T00:00:00Z' },
    { category: 'disk', severity: 'warning', message: 'disk low', timestamp: '2026-01-01T00:00:00Z' },
  ],
}

/** Route each endpoint independently so only the DELETE is made to fail. */
function routeFetch(deleteResponse: () => Response) {
  return vi.fn((url: string, init: RequestInit = {}) => {
    if (init.method === 'DELETE') return Promise.resolve(deleteResponse())
    if (String(url).includes('/monitoring/alerts')) {
      return Promise.resolve(jsonResponse(ALERTS))
    }
    return Promise.resolve(jsonResponse({}))
  })
}

function mountMonitor() {
  return mount(AlertsMonitor, { global: { plugins: [i18n] } })
}

async function clearAll(wrapper: ReturnType<typeof mountMonitor>) {
  const vm = wrapper.vm as unknown as { clearAlerts: () => Promise<void> }
  await vm.clearAlerts()
  await flushPromises()
}

describe('AlertsMonitor clear-all transport', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let originalLocation: Location

  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    setActivePinia(createPinia())
    vi.stubGlobal('confirm', vi.fn(() => true))

    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { pathname: '/monitoring/alerts', href: '' } as unknown as Location,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    })
  })

  it('tells the operator when a confirmed clear was rejected', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'alerts-token')
    fetchMock = routeFetch(() => jsonResponse({ detail: 'alert store read-only' }, 500))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountMonitor()
    await flushPromises()
    await clearAll(wrapper)

    const banner = wrapper.get('[data-testid="clear-alerts-error"]')
    expect(banner.text()).toContain('alert store read-only')
  })

  it('reports nothing when the clear succeeds', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'alerts-token')
    fetchMock = routeFetch(() => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountMonitor()
    await flushPromises()
    await clearAll(wrapper)

    expect(wrapper.find('[data-testid="clear-alerts-error"]').exists()).toBe(false)
  })

  it('sends the stored bearer on the destructive call, and to the API base', async () => {
    // `authStore.token` was null in this state, so the DELETE went out with no
    // credential at all.
    sessionStorage.setItem(TOKEN_KEY, 'alerts-token')
    fetchMock = routeFetch(() => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mountMonitor()
    await flushPromises()
    await clearAll(wrapper)

    const del = fetchMock.mock.calls.find((c) => (c[1] as RequestInit).method === 'DELETE')!
    expect(del[0]).toBe('/api/monitoring/alerts')
    expect((del[1].headers as Record<string, string>).Authorization).toBe('Bearer alerts-token')
    expect((del[1] as RequestInit).signal).toBeInstanceOf(AbortSignal)
  })

  it('does not clear alerts at all when the confirmation is declined', async () => {
    sessionStorage.setItem(TOKEN_KEY, 'alerts-token')
    fetchMock = routeFetch(() => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn(() => false))

    const wrapper = mountMonitor()
    await flushPromises()
    await clearAll(wrapper)

    expect(
      fetchMock.mock.calls.some((c) => (c[1] as RequestInit).method === 'DELETE')
    ).toBe(false)
  })
})
