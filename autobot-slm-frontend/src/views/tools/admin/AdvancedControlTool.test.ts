// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import AdvancedControlTool from './AdvancedControlTool.vue'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

// vue-i18n 11 requires app.use(); install a real i18n plugin since the
// template uses the global $t and the script uses useI18n().
const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

/** Route each advanced-control endpoint to a canned payload. */
function payloadFor(url: string): unknown {
  if (url.includes('/streaming/capabilities')) {
    return { vnc_available: true, novnc_available: true, max_sessions: 5, supported_resolutions: ['1024x768'], supported_depths: [24] }
  }
  if (url.includes('/streaming/sessions')) {
    return { sessions: [{ session_id: 's1', user_id: 'u1', display: ':1', vnc_port: 5901, status: 'active', created_at: '2026-01-01T00:00:00Z' }], count: 1 }
  }
  if (url.includes('/takeover/status')) return { active: true }
  if (url.includes('/takeover/pending')) {
    return { pending_requests: [{ request_id: 'r1', trigger: 'MANUAL_REQUEST', reason: 'why', priority: 'HIGH', created_at: '2026-01-01T00:00:00Z' }], count: 1 }
  }
  if (url.includes('/takeover/active')) {
    return { active_sessions: [{ session_id: 'as1', human_operator: 'op', status: 'active' }], count: 1 }
  }
  return { success: true }
}

function mountTool() {
  return mount(AdvancedControlTool, { global: { plugins: [i18n] } })
}

describe('AdvancedControlTool', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url: string) => ({
      ok: true,
      status: 200,
      json: async () => payloadFor(url),
    })) as unknown as typeof fetch
  })

  it('loads all advanced-control endpoints on mount via getBackendUrl', async () => {
    const wrapper = mountTool()
    await flushPromises()
    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0] as string)
    for (const suffix of ['/streaming/capabilities', '/streaming/sessions', '/takeover/status', '/takeover/pending', '/takeover/active']) {
      expect(calls.some((u) => u === `/autobot-api/advanced-control${suffix}`)).toBe(true)
    }
    // Rendered rows from the mocked payloads.
    expect(wrapper.text()).toContain('s1')
    expect(wrapper.text()).toContain('r1')
    expect(wrapper.text()).toContain('as1')
  })

  it('shows an error banner when a request fails', async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })) as unknown as typeof fetch
    const wrapper = mountTool()
    await flushPromises()
    expect(wrapper.find('[data-test="error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="error"]').text()).toContain('500')
  })

  it('POSTs to /streaming/create when creating a session', async () => {
    const wrapper = mountTool()
    await flushPromises()
    const userInput = wrapper.findAll('input').find((i) => i.attributes('required') !== undefined)
    await userInput!.setValue('alice')
    // jsdom does not auto-submit a form on submit-button click; trigger submit directly.
    await wrapper.findAll('form')[0].trigger('submit')
    await flushPromises()
    const post = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      (c) => c[0] === '/autobot-api/advanced-control/streaming/create' && c[1]?.method === 'POST',
    )
    expect(post).toBeTruthy()
    expect(JSON.parse(post![1]!.body as string)).toMatchObject({ user_id: 'alice' })
  })

  it('DELETEs on terminate', async () => {
    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('[data-test="terminate-s1"]').trigger('click')
    await flushPromises()
    const del = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
      (c) => c[0] === '/autobot-api/advanced-control/streaming/s1' && c[1]?.method === 'DELETE',
    )
    expect(del).toBeTruthy()
  })
})
