// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ChatApprovalSettings from './ChatApprovalSettings.vue'
import {
  AUTO_APPROVE_ATTACHMENT_KEY,
  RELAXED_CATEGORIES_KEY,
  parseAutoApprove,
  parseRelaxedCategories,
} from './chatApprovalSettings'
import en from '@/locales/en.json'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ getAuthHeaders: () => ({}) }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

type FetchMock = ReturnType<typeof vi.fn>

function stubSettings(stored: Record<string, string>): void {
  global.fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const key = decodeURIComponent(String(url).split('/api/settings/')[1] ?? '')
    if (init?.method === 'PUT') return { ok: true, status: 200, json: async () => ({ key, value: '' }) }
    if (key in stored) return { ok: true, status: 200, json: async () => ({ key, value: stored[key] }) }
    return { ok: false, status: 404, json: async () => ({}) }
  }) as unknown as typeof fetch
}

function puts(): Array<[string, RequestInit]> {
  return (global.fetch as FetchMock).mock.calls.filter((c) => c[1]?.method === 'PUT') as Array<[string, RequestInit]>
}

describe('ChatApprovalSettings', () => {
  beforeEach(() => stubSettings({}))

  it('shows auto-approve off by default with the risk stated', async () => {
    const wrapper = mount(ChatApprovalSettings, { global: { plugins: [i18n] } })
    await flushPromises()
    const sw = wrapper.find('[data-test="auto-approve-switch"]')
    expect(sw.attributes('aria-checked')).toBe('false')
    expect(wrapper.find('[data-test="auto-approve-risk"]').text()).toContain(
      'text inside an attached file could steer tools without anyone being asked',
    )
  })

  it('loads the stored relaxed categories and the stored auto-approve flag', async () => {
    stubSettings({
      [RELAXED_CATEGORIES_KEY]: JSON.stringify(['writing files']),
      [AUTO_APPROVE_ATTACHMENT_KEY]: JSON.stringify({ enabled: true }),
    })
    const wrapper = mount(ChatApprovalSettings, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.find('[data-test="relax-writing files"]').attributes('aria-checked')).toBe('true')
    expect(wrapper.find('[data-test="relax-publishing"]').attributes('aria-checked')).toBe('false')
    expect(wrapper.find('[data-test="auto-approve-switch"]').attributes('aria-checked')).toBe('true')
  })

  it('PUTs the relaxed categories as a JSON array on save', async () => {
    const wrapper = mount(ChatApprovalSettings, { global: { plugins: [i18n] } })
    await flushPromises()
    await wrapper.find('[data-test="relax-publishing"]').trigger('click')
    await wrapper.find('[data-test="save-relaxed"]').trigger('click')
    await flushPromises()
    expect(puts()).toHaveLength(1)
    expect(puts()[0][0]).toContain(`/api/settings/${RELAXED_CATEGORIES_KEY}`)
    expect(JSON.parse(JSON.parse(String(puts()[0][1].body)).value)).toEqual(['publishing'])
  })

  it('PUTs {"enabled": true} for the auto-approve flag, and only that key', async () => {
    const wrapper = mount(ChatApprovalSettings, { global: { plugins: [i18n] } })
    await flushPromises()
    await wrapper.find('[data-test="auto-approve-switch"]').trigger('click')
    await wrapper.find('[data-test="save-auto-approve"]').trigger('click')
    await flushPromises()
    expect(puts()).toHaveLength(1)
    expect(puts()[0][0]).toContain(`/api/settings/${AUTO_APPROVE_ATTACHMENT_KEY}`)
    expect(JSON.parse(JSON.parse(String(puts()[0][1].body)).value)).toEqual({ enabled: true })
  })
})

describe('stored value parsing', () => {
  it('reads both relaxed forms and drops unknown categories', () => {
    expect(parseRelaxedCategories(['publishing', 'nonsense'])).toEqual(['publishing'])
    expect(parseRelaxedCategories({ categories: ['writing data'] })).toEqual(['writing data'])
    expect(parseRelaxedCategories('publishing')).toEqual([])
    expect(parseRelaxedCategories(null)).toEqual([])
  })

  it('reads exactly true or {"enabled": true} as on', () => {
    expect(parseAutoApprove(true)).toBe(true)
    expect(parseAutoApprove({ enabled: true })).toBe(true)
    expect(parseAutoApprove({ enabled: 'yes' })).toBe(false)
    expect(parseAutoApprove('true')).toBe(false)
    expect(parseAutoApprove(false)).toBe(false)
    expect(parseAutoApprove(null)).toBe(false)
  })
})
