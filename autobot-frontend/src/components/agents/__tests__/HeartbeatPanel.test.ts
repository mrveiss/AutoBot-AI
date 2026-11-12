// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21136: the panel shows who paused an agent by name and never sends the actor itself.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const rawRequest = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { rawRequest: (...a: unknown[]) => rawRequest(...a) } }))
vi.mock('@/composables/useEventBus', () => ({
  useEventBus: () => ({ subscribe: () => () => {}, unsubscribe: vi.fn() }),
}))

import HeartbeatPanel from '../HeartbeatPanel.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function reply(body: unknown) {
  return { ok: true, status: 200, json: async () => body, text: async () => '' }
}

function config(over: Record<string, unknown>) {
  return {
    agent_id: 'a1',
    heartbeat_enabled: true,
    status: 'paused',
    paused_reason: 'r',
    paused_at: '2026-11-08T10:00:00Z',
    paused_by: 'principal-7',
    heartbeat_interval_seconds: 300,
    max_run_duration_seconds: 600,
    ...over,
  }
}

async function load(cfg: Record<string, unknown>) {
  rawRequest.mockImplementation(async (url: string) =>
    reply(url.endsWith('/config') ? cfg : []),
  )
  const wrapper = mount(HeartbeatPanel, { global: { plugins: [i18n] } })
  await wrapper.find('#agent-id-input').setValue('a1')
  await wrapper.find('.btn-load').trigger('click')
  await flushPromises()
  return wrapper
}

describe('HeartbeatPanel paused-by', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders the resolved display name, not the principal id', async () => {
    const w = await load(config({ paused_by_name: 'Alice A' }))
    expect(w.text()).toContain('Alice A')
    expect(w.text()).not.toContain('principal-7')
  })

  it('renders the translated System label for a system actor', async () => {
    const w = await load(config({ paused_by: 'system:budget', paused_by_name: null }))
    expect(w.text()).toContain('System')
    expect(w.text()).not.toContain('system:budget')
  })

  it('sends no paused_by when pausing', async () => {
    const w = await load(config({ status: 'active', paused_by: null }))
    await w.find('.btn-pause').trigger('click')
    await flushPromises()
    const call = rawRequest.mock.calls.find((c) => String(c[0]).endsWith('/pause'))
    expect(call).toBeDefined()
    expect(call![1].body).toEqual({ reason: 'Manual pause from UI' })
  })
})
