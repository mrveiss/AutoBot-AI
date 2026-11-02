// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * MonitoringView tabs (#18391 AC2): labels come from the locale, and the
 * admin-only sections (Backend Health, Agent ledger, Validation, Real user monitoring) are not offered to a
 * user the router guard would turn away.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import MonitoringView from './MonitoringView.vue'

const auth = { isAdmin: false }
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/stores/fleet', () => ({ useFleetStore: () => ({ nodeList: [] }) }))
vi.mock('@/composables/useFleetMetrics', () => ({
  useFleetMetrics: () => ({
    systemHealth: ref('healthy'),
    activeAlertCount: ref(0),
    poller: { pausedOnErrors: ref(false), start: vi.fn() },
  }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/monitoring/system' }),
  useRouter: () => ({ push: vi.fn() }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const TABS = en.monitoringView.tabs

async function tabLabels(isAdmin: boolean): Promise<string[]> {
  auth.isAdmin = isAdmin
  const w = mount(MonitoringView, { global: { plugins: [i18n], stubs: { 'router-view': true } } })
  await flushPromises()
  const labels = w.findAll('[role="tab"]').map((t) => t.text().trim())
  w.unmount()
  return labels
}

describe('MonitoringView tabs', () => {
  it('offers an admin every section, the agent ledger, validation and RUM included, labelled from the locale', async () => {
    expect(await tabLabels(true)).toEqual([
      TABS.system, TABS.logs, TABS.dashboards, TABS.alerts, TABS.errors, TABS.backendHealth, TABS.performance, TABS.agentLedger, TABS.validation, TABS.rum,
    ])
  })

  it('does not offer a non-admin the admin-only sections', async () => {
    const labels = await tabLabels(false)
    expect(labels).not.toContain(TABS.backendHealth)
    expect(labels).not.toContain(TABS.agentLedger)
    expect(labels).not.toContain(TABS.validation)
    expect(labels).not.toContain(TABS.rum)
    expect(labels).toContain(TABS.performance)
  })
})
