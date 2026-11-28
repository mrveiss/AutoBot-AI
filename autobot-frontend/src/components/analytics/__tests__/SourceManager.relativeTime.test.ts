// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** SourceManager (#19606): "synced <time> ago" comes from the kit's formatRelativeTime in the app locale. */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import SourceManager from '../SourceManager.vue'
import en from '@/i18n/locales/en.json'

const NOW = Date.parse('2026-11-02T12:00:00Z')
const at = (secondsAgo: number) => new Date(NOW - secondsAgo * 1000).toISOString()
let fetched: unknown[] = []

vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: vi.fn() }) }))
vi.mock('@/composables/analytics/useAnalyticsSourceManagement', () => ({
  useAnalyticsSourceManagement: () => ({
    isLoadingSources: ref(false),
    sourcesError: ref(null),
    fetchSources: async () => fetched,
    fetchQueueStatus: async () => null,
    fetchSourcesForPolling: async () => fetched,
    fetchQueueStatusForPolling: async () => null,
    syncSource: vi.fn(),
    deleteSource: vi.fn(),
    cancelQueueItem: vi.fn()
  })
}))

async function synced(secondsAgo: number, locale = 'en'): Promise<string> {
  vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
  fetched = [{ id: 'a', name: 'repo', source_type: 'github', status: 'idle', last_synced: at(secondsAgo) }]
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en } })
  const wrapper = mount(SourceManager, {
    props: { selectedSourceId: null, visible: false },
    global: { plugins: [i18n] },
    attachTo: document.body
  })
  await wrapper.setProps({ visible: true }) // the panel loads when it opens
  await flushPromises()
  const text = document.querySelector('.source-synced')?.textContent ?? '' // the panel is teleported to body
  wrapper.unmount()
  return text
}

describe('SourceManager relative time', () => {
  afterEach(() => vi.useRealTimers())

  it.each([
    [300, '5 minutes ago'],
    [7200, '2 hours ago'],
    [3 * 86400, '3 days ago'],
    [45 * 86400, '45 days ago']
  ])('%i seconds back reads %s', async (secondsAgo, expected) => {
    expect(await synced(secondsAgo)).toContain(expected)
  })

  it('follows the app locale, not English', async () => {
    expect(await synced(7200, 'de')).toContain('vor 2 Stunden')
  })
})
