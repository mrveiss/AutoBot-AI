// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** ConnectorStatusCard (#19606): "last sync" comes from the kit's createRecencyFormatter in the app locale. */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ConnectorStatusCard from '../ConnectorStatusCard.vue'
import type { ConnectorConfig, ConnectorStatus } from '@/types/knowledgeBase'

const NOW = Date.parse('2026-11-02T12:00:00Z')
const at = (secondsAgo: number) => new Date(NOW - secondsAgo * 1000).toISOString()

const lastSync = (lastSyncAt: string | null, locale = 'en'): string => {
  vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
  const config = { connector_id: 'c1', connector_type: 'web_crawler', name: 'Docs', enabled: true } as unknown as ConnectorConfig
  const status = {
    connector_id: 'c1', is_healthy: true, last_sync_at: lastSyncAt,
    last_sync_status: 'success', documents_indexed: 3, last_error: null
  } as ConnectorStatus
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en } })
  const wrapper = mount(ConnectorStatusCard, { props: { config, status }, global: { plugins: [i18n] } })
  const value = wrapper.findAll('.stat-value')[0]?.text() ?? ''
  wrapper.unmount()
  return value
}

describe('ConnectorStatusCard relative time', () => {
  afterEach(() => vi.useRealTimers())

  it.each([
    [30, 'just now'],
    [300, '5 minutes ago'],
    [7200, '2 hours ago'],
    [3 * 86400, '3 days ago']
  ])('%i seconds back reads %s', (secondsAgo, expected) => {
    expect(lastSync(at(secondsAgo))).toBe(expected)
  })

  it('reads a sync that never ran from the status text, not as a time', () => {
    expect(lastSync(null)).toBe(en.knowledge.connectors.status.never)
  })

  it('follows the app locale, not English', () => {
    const text = lastSync(at(7200), 'de')
    expect(text).toContain('vor 2')
    expect(text).not.toContain('ago')
  })
})
