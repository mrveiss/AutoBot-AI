// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19887 — a failed fleet-log read cleared `logs`, so the table showed "No logs
 * found" (the empty-result message) until the poller paused. A failed read must keep
 * the last good rows and raise a role="alert" load error; a genuinely empty read must
 * still say "No logs found" and show no error.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import LogViewer from './LogViewer.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const POLL_MS = 5000

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const ROW = {
  timestamp: '2026-01-01T00:00:00Z',
  severity: 'error',
  hostname: 'node-a',
  event_type: 'svc',
  message: 'disk almost full',
  event_id: 'e1',
  node_id: 'n1',
}

function isFleetLogs(url: string): boolean {
  return url.includes('/monitoring/logs')
}

function otherBody(url: string): unknown {
  return url.includes('/nodes') ? { nodes: [] } : {}
}

function stubFetch(respond: () => Response) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => (isFleetLogs(String(url)) ? respond() : jsonResponse(otherBody(String(url))))),
  )
}

function fleetAlerts(wrapper: ReturnType<typeof mount>) {
  return wrapper.findAll('[role="alert"]').filter(a => a.text().includes('Failed to load logs'))
}

describe('LogViewer failed read (#19887)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    setActivePinia(createPinia())
    sessionStorage.clear()
    localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('keeps the last good rows and shows a load error when a later read fails', async () => {
    let fail = false
    stubFetch(() => (fail ? jsonResponse({ detail: 'down' }, 500) : jsonResponse({ logs: [ROW] })))
    const wrapper = mount(LogViewer, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain('disk almost full')
    expect(fleetAlerts(wrapper)).toHaveLength(0)

    fail = true
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()
    expect(wrapper.text()).toContain('disk almost full')
    expect(wrapper.text()).not.toContain('No logs found')
    expect(fleetAlerts(wrapper)).toHaveLength(1)

    fail = false
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()
    expect(fleetAlerts(wrapper)).toHaveLength(0)
    wrapper.unmount()
  })

  it('shows a load error, not "No logs found", when the first read fails', async () => {
    stubFetch(() => jsonResponse({ detail: 'down' }, 500))
    const wrapper = mount(LogViewer, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(fleetAlerts(wrapper).length).toBeGreaterThan(0)
    expect(wrapper.text()).not.toContain('No logs found')
    wrapper.unmount()
  })

  it('shows "No logs found" and no error for a genuinely empty read', async () => {
    stubFetch(() => jsonResponse({ logs: [] }))
    const wrapper = mount(LogViewer, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.text()).toContain('No logs found')
    expect(fleetAlerts(wrapper)).toHaveLength(0)
    wrapper.unmount()
  })
})
