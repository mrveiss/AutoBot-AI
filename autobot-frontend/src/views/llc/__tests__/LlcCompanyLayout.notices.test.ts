// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21045: Company OS router notices reach the user as toasts.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { reactive, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { LLC_NOTICE_DEDUPE_MS } from '@/composables/useLlcCompanyNotices'

type Cb = (ev: { event_type: string; payload: Record<string, unknown> }) => void

const subscribe = vi.fn()
const notifyInfo = vi.fn()
const notifyWarning = vi.fn()
const notifyError = vi.fn()
const route = reactive<{ params: Record<string, string>; query: Record<string, string> }>({
  params: { companyId: 'c1' },
  query: {},
})
const store = reactive({
  selectedCompanyId: null as string | null,
  hasCompanies: true,
  isLoading: false,
  selectCompany: vi.fn(),
})

vi.mock('@/composables/useEventBus', () => ({ useEventBus: () => ({ subscribe }) }))
vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ notifyInfo, notifyWarning, notifyError }),
}))
vi.mock('vue-router', () => ({ useRoute: () => route }))
vi.mock('@/stores/useLlcCompanyStore', () => ({ useLlcCompanyStore: () => store }))

import LlcCompanyLayout from '@/views/llc/LlcCompanyLayout.vue'

const unsubs: Array<ReturnType<typeof vi.fn>> = []

function mountHost() {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  return mount(LlcCompanyLayout, {
    global: {
      plugins: [i18n],
      stubs: { LlcSidebar: true, PlanFirstProcessCard: true, RouterView: true },
    },
  })
}

const callback = (n = 0): Cb => subscribe.mock.calls[n][1] as Cb

/** Real wire shape: the publisher's envelope is the live event's `payload` (publisher.py). */
function wire(event_type: string, fields: Record<string, unknown> = {}) {
  return {
    event_type,
    payload: {
      event_type,
      company_id: 'c1',
      entity_type: 'agent',
      entity_id: 'e1',
      payload: fields,
      actor_id: null,
      ts: '2026-01-01T00:00:00Z',
    },
  }
}

describe('LlcCompanyLayout company notices (#21045)', () => {
  afterEach(() => vi.useRealTimers())

  beforeEach(() => {
    vi.clearAllMocks()
    unsubs.length = 0
    route.params.companyId = 'c1'
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    subscribe.mockImplementation(() => {
      const u = vi.fn()
      unsubs.push(u)
      return u
    })
  })

  it('warns with the dedicated string for an unfiled recovery', () => {
    mountHost()
    expect(subscribe).toHaveBeenCalledWith('company:c1', expect.any(Function))
    callback()(wire('heartbeat_missed', { agent_id: 'a7', reason: 'recovery_unfiled' }))
    expect(notifyWarning).toHaveBeenCalledWith(
      'Agent a7 timed out and no recovery item could be filed',
    )
  })

  it('does not dedupe alerts for different agents, but does for the same agent and reason', () => {
    mountHost()
    const fields = (agent_id: string) => ({ agent_id, reason: 'recovery_unfiled' })
    callback()(wire('heartbeat_missed', fields('a1')))
    callback()(wire('heartbeat_missed', fields('a2')))
    callback()(wire('heartbeat_missed', fields('a1')))
    expect(notifyWarning).toHaveBeenCalledTimes(2)
    expect(notifyWarning).toHaveBeenCalledWith('Agent a1 timed out and no recovery item could be filed')
    expect(notifyWarning).toHaveBeenCalledWith('Agent a2 timed out and no recovery item could be filed')
  })

  it('uses the generic key for an unknown type', () => {
    mountHost()
    callback()(wire('mystery_thing'))
    expect(notifyInfo).toHaveBeenCalledWith('A company update arrived')
  })

  it('ignores heartbeat_ok and activity events', () => {
    mountHost()
    callback()(wire('heartbeat_ok'))
    callback()(wire('llc:activity_created'))
    expect(notifyInfo).not.toHaveBeenCalled()
    expect(notifyWarning).not.toHaveBeenCalled()
    expect(notifyError).not.toHaveBeenCalled()
  })

  it('maps budget.hard_stop to a sticky error', () => {
    mountHost()
    callback()(wire('budget.hard_stop'))
    expect(notifyError).toHaveBeenCalledTimes(1)
  })

  it('re-subscribes on company change and unsubscribes on unmount', async () => {
    const wrapper = mountHost()
    route.params.companyId = 'c2'
    await nextTick()
    expect(unsubs[0]).toHaveBeenCalledTimes(1)
    expect(subscribe).toHaveBeenLastCalledWith('company:c2', expect.any(Function))
    wrapper.unmount()
    expect(unsubs[1]).toHaveBeenCalledTimes(1)
  })

  it('renders agent-less text and does not throw when agent_id is missing', () => {
    mountHost()
    expect(() => callback()(wire('work_item.handoff'))).not.toThrow()
    expect(notifyInfo).toHaveBeenCalledWith('A work item was handed over')
    callback()(wire('heartbeat_missed', { agent_id: 'a' }))
    expect(notifyWarning).toHaveBeenCalledWith('Agent a missed its heartbeat')
  })

  it('does not leak the raw type for approval_* and sprint_* events', () => {
    mountHost()
    callback()(wire('approval_requested'))
    callback()(wire('sprint_closed'))
    expect(notifyInfo).toHaveBeenCalledWith('An approval was updated')
    expect(notifyInfo).toHaveBeenCalledWith('A sprint was updated')
  })

  it('collapses a burst of identical events into one toast, then toasts again after the window', () => {
    mountHost()
    const windowMs = LLC_NOTICE_DEDUPE_MS
    const ev = wire('budget.hard_stop', { agent_id: 'a1' })
    for (let i = 0; i < 10; i++) callback()(ev)
    callback()(wire('budget.hard_stop', { agent_id: 'a2' }))
    expect(notifyError).toHaveBeenCalledTimes(2)
    vi.advanceTimersByTime(windowMs + 1)
    callback()(ev)
    expect(notifyError).toHaveBeenCalledTimes(3)
  })

  it.each([
    ['budget.soft_alert', 'warning'],
    ['budget.company_soft_alert', 'warning'],
    ['budget.hard_stop', 'error'],
    ['budget.company_hard_stop', 'error'],
    ['work_item.handoff_ready', 'info'],
    ['work_item.handoff', 'info'],
  ])('%s renders at %s level', (type, level) => {
    mountHost()
    callback()(wire(type, { agent_id: 'a1' }))
    const fns = { info: notifyInfo, warning: notifyWarning, error: notifyError }
    expect(fns[level as keyof typeof fns]).toHaveBeenCalledTimes(1)
    const msg = String(fns[level as keyof typeof fns].mock.calls[0][0])
    expect(msg).not.toContain(type)
  })

  it('shows one sticky error for repeated company hard stops', () => {
    mountHost()
    for (let i = 0; i < 5; i++) callback()(wire('budget.company_hard_stop'))
    expect(notifyError).toHaveBeenCalledTimes(1)
    expect(notifyError).toHaveBeenCalledWith(
      'Budget exhausted: agents are stopped until the budget is raised',
    )
  })
})
