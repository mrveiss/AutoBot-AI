// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useChatCompanyScope (#21997): switching the active company reloads the chat list and closes an open chat
// of another company; assignment is an explicit call through ApiClient.assignChatCompany, never automatic.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const h = vi.hoisted(() => ({
  store: { sessions: [] as { id: string; unassigned?: boolean }[], currentSessionId: 'a' as string | null },
  controller: { loadChatSessions: vi.fn(), switchToSession: vi.fn() },
  company: { selectedCompanyId: 'co-1', companies: [{ id: 'co-2', name: 'Beta' }], hasCompanies: true, fetchCompanies: vi.fn() },
  assign: vi.fn(),
  showToast: vi.fn(),
}))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => h.store }))
vi.mock('@/models/controllers', () => ({ useChatController: () => h.controller }))
vi.mock('@/stores/useLlcCompanyStore', () => ({ useLlcCompanyStore: () => h.company }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: h.showToast }) }))
vi.mock('@/utils/ApiClient', () => ({ default: { assignChatCompany: h.assign } }))

import { useChatCompanyScope } from '../useChatCompanyScope'

function setup() {
  let api!: ReturnType<typeof useChatCompanyScope>
  mount({ setup() { api = useChatCompanyScope(); return () => null } }, {
    global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
  })
  return api
}

beforeEach(() => {
  // vitest.config mockReset wipes the defaults, so each test re-applies them (#3070).
  h.company = reactive({ selectedCompanyId: 'co-1', companies: [{ id: 'co-2', name: 'Beta' }], hasCompanies: true, fetchCompanies: vi.fn() })
  h.store.sessions = [{ id: 'a' }]
  h.store.currentSessionId = 'a'
  h.controller.loadChatSessions.mockResolvedValue(undefined)
  h.controller.switchToSession.mockResolvedValue(undefined)
  h.assign.mockResolvedValue({})
})

describe('company switch', () => {
  it('reloads the list in place and leaves an open chat of the other company closed', async () => {
    setup()
    h.company.selectedCompanyId = 'co-2'
    await nextTick(); await flushPromises()
    expect(h.controller.loadChatSessions).toHaveBeenCalledTimes(1)
    expect(h.controller.switchToSession).not.toHaveBeenCalled()
  })

  it('keeps the open chat when it is Unassigned, which every company lists', async () => {
    h.controller.loadChatSessions.mockImplementation(async () => { h.store.sessions = [{ id: 'a', unassigned: true }] })
    setup()
    h.company.selectedCompanyId = 'co-2'
    await nextTick(); await flushPromises()
    expect(h.controller.switchToSession).toHaveBeenCalledWith('a')
  })

  it('does nothing when the company did not change', async () => {
    setup()
    await nextTick(); await flushPromises()
    expect(h.controller.loadChatSessions).not.toHaveBeenCalled()
  })
})

describe('assignment', () => {
  it('assigns through ApiClient.assignChatCompany only when called, then reloads the list', async () => {
    const api = setup()
    expect(h.assign).not.toHaveBeenCalled()
    expect(await api.assignToCompany('u1', 'co-2')).toBe(true)
    expect(h.assign).toHaveBeenCalledWith('u1', 'co-2')
    expect(h.controller.loadChatSessions).toHaveBeenCalled()
  })

  it('reports a refused assignment and does not reload', async () => {
    h.assign.mockRejectedValue(new Error('409'))
    const api = setup()
    expect(await api.assignToCompany('u1', 'co-2')).toBe(false)
    expect(h.showToast).toHaveBeenCalledWith(en.chat.sidebar.assignFailed, 'error')
    expect(h.controller.loadChatSessions).not.toHaveBeenCalled()
  })
})
