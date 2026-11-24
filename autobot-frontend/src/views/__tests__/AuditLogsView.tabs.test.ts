// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The event-log and command-history tabs of the audit screen are shown to admins only; the backend
// (`check_admin_permission` on both routes) stays the real gate.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { useUserStore } from '@/stores/useUserStore'
import AuditLogsView from '../AuditLogsView.vue'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

vi.mock('@/composables/useAuditApi', async () => {
  const { ref } = await import('vue')
  const noop = vi.fn()
  return {
    useAuditState: () => ({
      entries: ref([]), failureEntries: ref([]), statisticsFailed: ref(false), resolvedStatistics: ref(null),
      vmInfo: ref(null), operationCategories: ref([]), loading: ref(false), loadingStats: ref(false),
      hasMore: ref(false), filter: ref({}), currentPage: ref(1), isPolling: ref(false), sessionTrail: ref([]),
      userTrail: ref([]), loadingTrail: ref(false), loadLogs: noop, loadStatistics: noop,
      loadOperationCategories: noop, loadSessionTrail: noop, loadUserTrail: noop, loadFailedOperations: noop,
      cleanupLogs: noop, setFilter: noop, resetFilter: noop, nextPage: noop, prevPage: noop, startPolling: noop,
      stopPolling: noop, downloadExport: noop,
    }),
  }
})

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })

function render(role: 'admin' | 'user') {
  const store = useUserStore()
  store.currentUser = { id: '1', username: 'u', role } as never
  return mount(AuditLogsView, {
    global: {
      plugins: [i18n],
      stubs: {
        AuditStatistics: true, AuditFilters: true, AuditLogTable: true, AuditTimeline: true, BaseModal: true,
        BaseButton: true, Icon: true, AuditEventLogsPanel: { template: '<div data-testid="event-panel" />' },
        AuditCommandHistoryPanel: { template: '<div data-testid="history-panel" />' },
      },
    },
  })
}
const tab = (w: ReturnType<typeof render>, text: string) => w.findAll('.tab-btn').find((b) => b.text() === text)

describe('AuditLogsView admin tabs', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('shows both tabs to an admin and opens each panel', async () => {
    const w = render('admin')
    await flushPromises()

    await tab(w, en.views.auditLogs.eventLogs)!.trigger('click')
    expect(w.find('[data-testid="event-panel"]').exists()).toBe(true)
    await tab(w, en.views.auditLogs.commandHistory)!.trigger('click')
    expect(w.find('[data-testid="history-panel"]').exists()).toBe(true)
  })

  it('shows neither tab to a non-admin', async () => {
    const w = render('user')
    await flushPromises()

    expect(tab(w, en.views.auditLogs.eventLogs)).toBeUndefined()
    expect(tab(w, en.views.auditLogs.commandHistory)).toBeUndefined()
  })
})
