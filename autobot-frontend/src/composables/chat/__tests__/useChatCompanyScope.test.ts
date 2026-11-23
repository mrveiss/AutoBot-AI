// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// useChatCompanyScope (#21997): switching the active company reloads the chat list and closes an open chat
// of another company; assignment is an explicit call through ApiClient.assignChatCompany, never automatic.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, reactive } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '@/stores/useChatStore'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const h = vi.hoisted(() => ({
  controller: { loadChatSessions: vi.fn(), switchToSession: vi.fn() },
  company: { selectedCompanyId: 'co-1', companies: [{ id: 'co-2', name: 'Beta' }], hasCompanies: true, fetchCompanies: vi.fn() },
  assign: vi.fn(),
  showToast: vi.fn(),
}))
vi.mock('@/models/controllers', () => ({ useChatController: () => h.controller }))
vi.mock('@/stores/useLlcCompanyStore', () => ({ useLlcCompanyStore: () => h.company }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast: h.showToast }) }))
vi.mock('@/utils/ApiClient', () => ({ default: { assignChatCompany: h.assign } }))

import { useChatCompanyScope } from '../useChatCompanyScope'

// The REAL chat store: the close on a company switch is asserted on its currentSessionId.
const chat = (id: string, unassigned = false) => ({ id, title: id, messages: [], isActive: false, unassigned })
function open(id: string, ...listed: ReturnType<typeof chat>[]) {
  const store = useChatStore()
  listed.forEach((c) => store.importSession(c))
  store.currentSessionId = id
  return store
}

function setup() {
  let api!: ReturnType<typeof useChatCompanyScope>
  mount({ setup() { api = useChatCompanyScope(); return () => null } }, {
    global: { plugins: [createI18n({ legacy: false, locale: 'en', messages: { en } })] },
  })
  return api
}

beforeEach(() => {
  setActivePinia(createPinia())
  // vitest.config mockReset wipes the defaults, so each test re-applies them (#3070).
  h.company = reactive({ selectedCompanyId: 'co-1', companies: [{ id: 'co-2', name: 'Beta' }], hasCompanies: true, fetchCompanies: vi.fn() })
  h.controller.loadChatSessions.mockResolvedValue(undefined)
  h.controller.switchToSession.mockResolvedValue(undefined)
  h.assign.mockResolvedValue({})
})

describe('company switch', () => {
  it('closes an open chat of the other company and reloads the list in place', async () => {
    const store = open('a', chat('a'))
    setup()
    h.company.selectedCompanyId = 'co-2'
    await nextTick(); await flushPromises()
    expect(store.currentSessionId).toBeNull()
    expect(h.controller.loadChatSessions).toHaveBeenCalledWith(true)
  })

  it('keeps the open chat when it is Unassigned, which every company lists', async () => {
    const store = open('a', chat('a', true))
    setup()
    h.company.selectedCompanyId = 'co-2'
    await nextTick(); await flushPromises()
    expect(store.currentSessionId).toBe('a')
    expect(h.controller.loadChatSessions).toHaveBeenCalledWith(true)
  })

  it('does nothing when the company did not change', async () => {
    const store = open('a', chat('a'))
    setup()
    await nextTick(); await flushPromises()
    expect(h.controller.loadChatSessions).not.toHaveBeenCalled()
    expect(store.currentSessionId).toBe('a')
  })
})

describe('assignment', () => {
  it('assigns through ApiClient.assignChatCompany only when called, then reloads keeping the open chat', async () => {
    const store = open('y', chat('y'), chat('u1', true))
    const api = setup()
    expect(h.assign).not.toHaveBeenCalled()
    expect(await api.assignToCompany('u1', 'co-2')).toBe(true)
    expect(h.assign).toHaveBeenCalledWith('u1', 'co-2')
    expect(h.controller.loadChatSessions).toHaveBeenCalledWith(true)
    expect(store.currentSessionId).toBe('y')
  })

  it('reports a refused assignment and does not reload', async () => {
    h.assign.mockRejectedValue(new Error('409'))
    const api = setup()
    expect(await api.assignToCompany('u1', 'co-2')).toBe(false)
    expect(h.showToast).toHaveBeenCalledWith(en.chat.sidebar.assignFailed, 'error')
    expect(h.controller.loadChatSessions).not.toHaveBeenCalled()
  })
})
