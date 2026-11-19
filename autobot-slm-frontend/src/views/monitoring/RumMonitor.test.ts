// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * RumMonitor (#18277): the collected data from /rum/status + /rum/export, each state said apart
 * (reading, failed, collecting-but-empty, off-and-empty, data held but unreadable), collection
 * turned on through /rum/config with the whole current config and off through /rum/disable, and
 * "Clear" only ever sent after the confirmation.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { HttpError } from '@autobot/ui'
import RumMonitor from './RumMonitor.vue'
import en from '@/locales/en.json'

const client = { get: vi.fn(), post: vi.fn() }
vi.mock('@/composables/useAutobotApi', () => ({ createAutobotBackendClient: () => client }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const L = en.monitoring.rum

const config = {
  enabled: true, error_tracking: true, performance_monitoring: true, interaction_tracking: false, session_recording: false,
  sample_rate: 100, max_events_per_session: 1000, debug_mode: false, log_to_backend: true, log_level: 'info',
}
const stats = { total_events: 3, total_sessions: 2, active_sessions: 1, events_today: 2 }

function rumStatus(overrides: { enabled?: boolean; statistics?: Partial<typeof stats> } = {}) {
  const enabled = overrides.enabled ?? true
  return { status: 'success', rum_status: { enabled, config: { ...config, enabled }, statistics: { ...stats, ...overrides.statistics } } }
}

const event = (type: string, url: string, sessionId: string, at: string) => ({
  type, timestamp: at, sessionId, url, userAgent: 'UA', server_timestamp: at, data: {},
})
const exported = {
  status: 'success',
  data: {
    export_timestamp: '2026-11-01T10:00:00+00:00',
    config,
    sessions: {
      'sess-old': { start_time: '2026-11-01T08:00:00+00:00', last_activity: '2026-11-01T08:30:00+00:00', event_count: 1, user_agent: 'Old UA', initial_url: 'https://app.example/old' },
      'sess-new': { start_time: '2026-11-01T09:00:00+00:00', last_activity: '2026-11-01T09:59:00+00:00', event_count: 2, user_agent: 'New UA', initial_url: 'https://app.example/new' },
    },
    events: [
      event('performance', 'https://app.example/old', 'sess-old', '2026-11-01T08:30:00+00:00'),
      event('javascript_error', 'https://app.example/new', 'sess-new', '2026-11-01T09:58:00+00:00'),
      event('javascript_error', 'https://app.example/new', 'sess-new', '2026-11-01T09:59:00+00:00'),
    ],
    summary: { total_events: 3, total_sessions: 2, event_types: { performance: 1, javascript_error: 2 } },
  },
}

let wrapper: VueWrapper | undefined
let current: { status: unknown; export: unknown }

function serve(next: Partial<typeof current> = {}): void {
  current = { status: rumStatus(), export: exported, ...next }
  client.get.mockImplementation(async (url: string) => {
    const body = url === '/rum/status' ? current.status : url === '/rum/export' ? current.export : undefined
    if (body === undefined) throw new Error(`unrouted ${url}`)
    if (body instanceof Error) throw body
    return body
  })
}

async function mountView(): Promise<VueWrapper> {
  wrapper = mount(RumMonitor, { global: { plugins: [i18n], stubs: { teleport: true } } })
  await flushPromises()
  return wrapper
}

const byId = (w: VueWrapper, id: string) => w.find(`[data-testid="${id}"]`)
const posts = () => client.post.mock.calls.map((c) => c[0])

beforeEach(() => {
  client.get.mockReset()
  client.post.mockReset()
  serve()
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('RumMonitor data', () => {
  it('reads /rum/status and /rum/export and shows the counts, types, sessions and latest events', async () => {
    const w = await mountView()
    expect(client.get).toHaveBeenCalledWith('/rum/status', { maxRetries: 1 })
    expect(client.get).toHaveBeenCalledWith('/rum/export', { maxRetries: 1 })
    expect(byId(w, 'slm-rum-stat-total_events').text()).toContain('3')
    expect(byId(w, 'slm-rum-stat-active_sessions').text()).toContain('1')
    expect(byId(w, 'slm-rum-state').text()).toBe(L.collection.on)
    expect(byId(w, 'slm-rum-types').text()).toContain('javascript_error')
    const sessions = byId(w, 'slm-rum-sessions').findAll('tbody tr').map((r) => r.text())
    expect(sessions[0]).toContain('sess-new')
    expect(sessions[1]).toContain('sess-old')
    expect(byId(w, 'slm-rum-events-note').text()).toBe('Showing the latest 3 of 3 events held.')
    expect(byId(w, 'slm-rum-events').findAll('tbody tr')).toHaveLength(3)
    expect(byId(w, 'slm-rum-setting-sample_rate').text()).toContain('100')
    expect(byId(w, 'slm-rum-setting-debug_mode').text()).toContain(L.no)
  })

  it('shows the browser-sent text as text, not markup', async () => {
    serve({ export: { ...exported, data: { ...exported.data, events: [event('x', '<img src=x onerror=alert(1)>', 's', '2026-11-01T09:59:00+00:00')] } } })
    const w = await mountView()
    expect(w.find('img').exists()).toBe(false)
    expect(byId(w, 'slm-rum-events').text()).toContain('<img src=x')
  })

  it('shows a reading state until the status answers', async () => {
    client.get.mockImplementation(() => new Promise(() => {}))
    wrapper = mount(RumMonitor, { global: { plugins: [i18n], stubs: { teleport: true } } })
    await flushPromises()
    expect(byId(wrapper, 'slm-rum-loading').text()).toContain(L.loading)
    expect(byId(wrapper, 'slm-rum-collection').exists()).toBe(false)
  })
})

describe('RumMonitor empty and failed', () => {
  it('says collecting-but-nothing-yet when collection is on and nothing is held, without reading the export', async () => {
    serve({ status: rumStatus({ statistics: { total_events: 0, total_sessions: 0, active_sessions: 0, events_today: 0 } }) })
    const w = await mountView()
    expect(byId(w, 'slm-rum-empty').text()).toContain(L.emptyOnTitle)
    expect(client.get).not.toHaveBeenCalledWith('/rum/export', expect.anything())
    expect(byId(w, 'slm-rum-clear').attributes('disabled')).toBeDefined()
  })

  it('says collection is off and nothing is held when it is off', async () => {
    serve({ status: rumStatus({ enabled: false, statistics: { total_events: 0, total_sessions: 0, active_sessions: 0, events_today: 0 } }) })
    const w = await mountView()
    expect(byId(w, 'slm-rum-empty').text()).toContain(L.emptyOffTitle)
    expect(byId(w, 'slm-rum-state').text()).toBe(L.collection.off)
  })

  it('says the status read failed, with no data and no controls', async () => {
    serve({ status: new HttpError(500, 'Internal Server Error') })
    const w = await mountView()
    expect(byId(w, 'slm-rum-error').text()).toContain(L.errorTitle)
    expect(byId(w, 'slm-rum-collection').exists()).toBe(false)
    expect(byId(w, 'slm-rum-empty').exists()).toBe(false)
  })

  it('keeps the counts and says the data could not be read when only the export fails', async () => {
    serve({ export: new HttpError(403, 'Forbidden', { detail: 'Admin permission required' }) })
    const w = await mountView()
    expect(byId(w, 'slm-rum-detail-error').text()).toContain('Admin permission required')
    expect(byId(w, 'slm-rum-stat-total_events').text()).toContain('3')
    expect(byId(w, 'slm-rum-empty').exists()).toBe(false)
    expect(byId(w, 'slm-rum-events').exists()).toBe(false)
  })
})

describe('RumMonitor collection switch', () => {
  it('turns collection on through /rum/config with the whole current config', async () => {
    serve({ status: rumStatus({ enabled: false }) })
    client.post.mockResolvedValue({ status: 'success', message: 'RUM configuration updated', config: { ...config, enabled: true } })
    const w = await mountView()
    await byId(w, 'slm-rum-switch').trigger('click')
    await flushPromises()
    expect(client.post).toHaveBeenCalledWith('/rum/config', { ...config, enabled: true })
    expect(byId(w, 'slm-rum-notice').text()).toContain(L.collection.enabledOk)
  })

  it('turns collection off through /rum/disable', async () => {
    client.post.mockResolvedValue({ status: 'success', message: 'RUM monitoring disabled' })
    const w = await mountView()
    await byId(w, 'slm-rum-switch').trigger('click')
    await flushPromises()
    expect(posts()).toEqual(['/rum/disable'])
    expect(byId(w, 'slm-rum-notice').text()).toContain(L.collection.disabledOk)
  })

  it('says the switch failed and leaves the collection state as it was', async () => {
    client.post.mockRejectedValue(new HttpError(500, 'Internal Server Error'))
    const w = await mountView()
    await byId(w, 'slm-rum-switch').trigger('click')
    await flushPromises()
    expect(byId(w, 'slm-rum-notice').text()).toContain(L.collection.disableFailed)
    expect(byId(w, 'slm-rum-state').text()).toBe(L.collection.on)
  })
})

describe('RumMonitor clear', () => {
  it('sends nothing until the confirmation, and cancel sends nothing', async () => {
    const w = await mountView()
    await byId(w, 'slm-rum-clear').trigger('click')
    await flushPromises()
    expect(byId(w, 'slm-rum-confirm-body').text()).toBe('This permanently removes 3 events and 2 sessions. It cannot be undone.')
    expect(client.post).not.toHaveBeenCalled()
    await byId(w, 'slm-rum-confirm-cancel').trigger('click')
    await flushPromises()
    expect(client.post).not.toHaveBeenCalled()
    expect(byId(w, 'slm-rum-confirm-body').exists()).toBe(false)
  })

  it('POSTs /rum/clear once confirmed, says what was cleared, and re-reads the empty store', async () => {
    client.post.mockImplementation(async () => {
      serve({ status: rumStatus({ statistics: { total_events: 0, total_sessions: 0, active_sessions: 0, events_today: 0 } }) })
      return { status: 'success', message: 'RUM data cleared', events_cleared: 3, sessions_cleared: 2 }
    })
    const w = await mountView()
    await byId(w, 'slm-rum-clear').trigger('click')
    await byId(w, 'slm-rum-confirm-clear').trigger('click')
    await flushPromises()
    expect(posts()).toEqual(['/rum/clear'])
    expect(byId(w, 'slm-rum-notice').text()).toContain('Cleared 3 events and 2 sessions.')
    expect(byId(w, 'slm-rum-empty').exists()).toBe(true)
    expect(byId(w, 'slm-rum-confirm-body').exists()).toBe(false)
  })

  it('says the clear failed and keeps the held data on screen', async () => {
    client.post.mockRejectedValue(new HttpError(500, 'Internal Server Error'))
    const w = await mountView()
    await byId(w, 'slm-rum-clear').trigger('click')
    await byId(w, 'slm-rum-confirm-clear').trigger('click')
    await flushPromises()
    expect(byId(w, 'slm-rum-notice').text()).toContain(L.clear.failed)
    expect(byId(w, 'slm-rum-stat-total_events').text()).toContain('3')
  })
})
