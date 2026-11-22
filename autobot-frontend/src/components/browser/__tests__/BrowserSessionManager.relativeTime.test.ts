// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** BrowserSessionManager (#19606): "active <time> ago" comes from the kit's formatRelativeTime in the app locale. */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import BrowserSessionManager from '../BrowserSessionManager.vue'
import en from '@/i18n/locales/en.json'

const NOW = Date.parse('2026-11-02T12:00:00Z')
const at = (secondsAgo: number) => new Date(NOW - secondsAgo * 1000).toISOString()
const sessions = ref<unknown[]>([])

vi.mock('@/composables/useBrowserAutomation', () => ({
  useBrowserAutomation: () => ({ sessions, launchSession: vi.fn(), closeSession: vi.fn(), deleteSession: vi.fn() })
}))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: vi.fn() }) }))

const activeLine = (secondsAgo: number, locale = 'en'): string => {
  vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
  sessions.value = [
    { id: 's1', url: 'https://example.com', status: 'active', created_at: at(secondsAgo), last_activity: at(secondsAgo) }
  ]
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en } })
  const wrapper = mount(BrowserSessionManager, { global: { plugins: [i18n] } })
  const lines = wrapper.findAll('.info-item span').map((s) => s.text())
  wrapper.unmount()
  return lines.find((l) => !l.startsWith('Created')) ?? ''
}

describe('BrowserSessionManager relative time', () => {
  afterEach(() => vi.useRealTimers())

  it.each([
    [30, '30 seconds ago'],
    [300, '5 minutes ago'],
    [7200, '2 hours ago'],
    [3 * 86400, '3 days ago'],
    [45 * 86400, '45 days ago']
  ])('%i seconds back reads %s', (secondsAgo, expected) => {
    expect(activeLine(secondsAgo)).toContain(expected)
  })

  it('follows the app locale, not English', () => {
    expect(activeLine(7200, 'de')).toContain('vor 2 Stunden')
  })
})
