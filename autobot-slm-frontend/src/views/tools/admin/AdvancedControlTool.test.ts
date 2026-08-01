// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import axios from 'axios'
import AdvancedControlTool from './AdvancedControlTool.vue'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

// #12653: the tool now reaches the autobot backend through `useAutobotApi`,
// the SLM app's single client for that backend, instead of a private `fetch`.
// Stubbing `axios.create` keeps the assertions on the exact endpoint paths and
// HTTP verbs — the transport changed, the wire contract did not.
vi.mock('axios', () => {
  const instance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  }
  return { default: { create: vi.fn(() => instance) } }
})

// vue-i18n 11 requires app.use(); install a real i18n plugin since the
// template uses the global $t and the script uses useI18n().
const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

type MockedClient = {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}

/** The single axios instance every `useAutobotApi()` call receives. */
function client(): MockedClient {
  return (axios.create as unknown as () => MockedClient)()
}

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
    const c = client()
    c.get.mockReset()
    c.post.mockReset()
    c.delete.mockReset()
    c.get.mockImplementation(async (url: string) => ({ data: payloadFor(url) }))
    c.post.mockImplementation(async (url: string) => ({ data: payloadFor(url) }))
    c.delete.mockImplementation(async (url: string) => ({ data: payloadFor(url) }))
  })

  it('loads all advanced-control endpoints on mount via useAutobotApi', async () => {
    const wrapper = mountTool()
    await flushPromises()
    const calls = client().get.mock.calls.map((c) => c[0] as string)
    for (const suffix of ['/streaming/capabilities', '/streaming/sessions', '/takeover/status', '/takeover/pending', '/takeover/active']) {
      expect(calls).toContain(`/advanced-control${suffix}`)
    }
    // Rendered rows from the mocked payloads.
    expect(wrapper.text()).toContain('s1')
    expect(wrapper.text()).toContain('r1')
    expect(wrapper.text()).toContain('as1')
  })

  it('shows an error banner when a request fails', async () => {
    client().get.mockRejectedValue({ response: { status: 500 } })
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
    const post = client().post.mock.calls.find((c) => c[0] === '/advanced-control/streaming/create')
    expect(post).toBeTruthy()
    expect(post![1]).toMatchObject({ user_id: 'alice' })
  })

  it('DELETEs on terminate', async () => {
    const wrapper = mountTool()
    await flushPromises()
    await wrapper.find('[data-test="terminate-s1"]').trigger('click')
    await flushPromises()
    const del = client().delete.mock.calls.find((c) => c[0] === '/advanced-control/streaming/s1')
    expect(del).toBeTruthy()
  })

  it('approves a pending takeover through the shared client', async () => {
    const wrapper = mountTool()
    await flushPromises()
    const operatorInput = wrapper.findAll('input').find((i) => i.attributes('placeholder') === en.tools.admin.advancedControlTool.operatorPlaceholder)
    await operatorInput!.setValue('op-1')
    await wrapper.find('[data-test="approve-r1"]').trigger('click')
    await flushPromises()
    const approve = client().post.mock.calls.find((c) => c[0] === '/advanced-control/takeover/r1/approve')
    expect(approve).toBeTruthy()
    expect(approve![1]).toMatchObject({ human_operator: 'op-1' })
  })
})
