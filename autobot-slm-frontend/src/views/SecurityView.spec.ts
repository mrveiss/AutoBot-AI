// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Proves the page-nav controls added in #12044. SecurityView paginates the
// audit logs / security events / policies server-side but previously rendered
// only a static "showing N of total" banner with no way to move past page 1.
// This test drives the audit-log list: the Next control must advance the page
// state and re-fetch the endpoint with the incremented page number.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import SecurityView from './SecurityView.vue'
import en from '@/locales/en.json'

// Pin the route to the audit tab so the audit panel (and its pagination) render.
const route = { params: { tab: 'audit' } }
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: vi.fn() }),
}))

// 120 total logs at perPage 50 -> 3 pages, so hasNext is true on page 1.
const AUDIT_TOTAL = 120
const getAuditLogs = vi.fn(async (page: number) => ({
  logs: Array.from({ length: 50 }, (_, i) => ({
    log_id: `log-${page}-${i}`,
    timestamp: new Date().toISOString(),
    username: 'admin',
    category: 'security',
    action: 'view',
    resource_type: 'node',
    success: true,
  })),
  total: AUDIT_TOTAL,
}))

vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({
    getSecurityOverview: vi.fn(async () => ({
      security_score: 100,
      active_threats: 0,
      failed_logins_24h: 0,
      policy_violations: 0,
      recent_events: [],
    })),
    getAuditLogs,
  }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountView() {
  return mount(SecurityView, { global: { plugins: [i18n] } })
}

describe('SecurityView audit-log pagination (#12044)', () => {
  beforeEach(() => {
    getAuditLogs.mockClear()
  })

  it('renders a Next control and re-fetches the next page when clicked', async () => {
    const wrapper = mountView()
    await flushPromises()

    // Load the first page of audit logs via the tab (onTabChange -> fetch page 1).
    const auditTab = wrapper.findAll('button').find((b) => b.text() === 'Audit Logs')
    expect(auditTab).toBeTruthy()
    await auditTab!.trigger('click')
    await flushPromises()

    expect(getAuditLogs).toHaveBeenCalledTimes(1)
    expect(getAuditLogs.mock.calls[0][0]).toBe(1)

    // The Next control only exists because total (120) exceeds perPage (50).
    const nextBtn = wrapper.findAll('button').find((b) => b.text() === 'Next')
    expect(nextBtn).toBeTruthy()

    await nextBtn!.trigger('click')
    await flushPromises()

    // Navigation must advance the page and re-fetch with page 2.
    expect(getAuditLogs).toHaveBeenCalledTimes(2)
    expect(getAuditLogs.mock.calls[1][0]).toBe(2)
  })

  it('disables Previous on the first page', async () => {
    const wrapper = mountView()
    await flushPromises()
    const auditTab = wrapper.findAll('button').find((b) => b.text() === 'Audit Logs')
    await auditTab!.trigger('click')
    await flushPromises()

    const prevBtn = wrapper.findAll('button').find((b) => b.text() === 'Previous')
    expect(prevBtn).toBeTruthy()
    expect(prevBtn!.attributes('disabled')).toBeDefined()
  })
})
