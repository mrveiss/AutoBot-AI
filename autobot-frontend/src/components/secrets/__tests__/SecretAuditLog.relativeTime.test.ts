// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** SecretAuditLog (#19606): the time column comes from the kit's createRecencyFormatter in the app locale. */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import SecretAuditLog from '../SecretAuditLog.vue'

const NOW = Date.parse('2026-11-02T12:00:00Z')
const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))

const row = (secondsAgo: number) => ({
  id: '6f1c2f0e-8f44-4f55-a0a1-2f3a5b7c9d10',
  timestamp: (NOW - secondsAgo * 1000) / 1000, // the backend sends epoch seconds
  date: '2026-11-02',
  operation: 'secret.create',
  result: 'success',
  user_id: 'alice',
  ip_address: null,
  session_id: null,
  user_role: null,
  resource: null,
  vm_source: 'main',
  vm_name: 'backend',
  details: { name: 'prod-db-credential' },
  performance_ms: null
})

const rendered = async (secondsAgo: number, locale = 'en'): Promise<string> => {
  vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
  get.mockResolvedValue({ success: true, total_returned: 1, has_more: false, entries: [row(secondsAgo)], query: {} })
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en } })
  const wrapper = mount(SecretAuditLog, { global: { plugins: [i18n] } })
  await flushPromises()
  const text = wrapper.text()
  wrapper.unmount()
  return text
}

describe('SecretAuditLog relative time', () => {
  afterEach(() => vi.useRealTimers())

  it.each([
    [30, 'just now'],
    [300, '5m ago'],
    [7200, '2h ago']
  ])('%i seconds back reads %s', async (secondsAgo, expected) => {
    expect(await rendered(secondsAgo)).toContain(expected)
  })

  it('shows a short date and time from a day on, not relative text', async () => {
    const text = await rendered(3 * 86400)
    expect(text).toContain('Oct')
    expect(text).not.toContain('ago')
  })

  it('follows the app locale, not English', async () => {
    const text = await rendered(7200, 'de')
    expect(text).toContain('vor 2')
    expect(text).not.toContain('2h ago')
  })
})
