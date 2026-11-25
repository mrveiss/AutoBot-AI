// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The event-log and command-history panels of the audit screen: each loads on mount through useAuditApi, and
// shows loading, empty, error and data states. The admin-only tabs of AuditLogsView follow the user's role.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import { formatDateTime } from '@/utils/formatHelpers'
import AuditEventLogsPanel from '../AuditEventLogsPanel.vue'
import AuditCommandHistoryPanel from '../AuditCommandHistoryPanel.vue'

const { queryEventLogs, getCommandHistory } = vi.hoisted(() => ({ queryEventLogs: vi.fn(), getCommandHistory: vi.fn() }))

vi.mock('@/composables/useAuditApi', () => ({ useAuditApi: () => ({ queryEventLogs, getCommandHistory }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })
const render = (c: object) => mount(c, { global: { plugins: [i18n] } })

const EVENTS = {
  events: [{ id: 'e1', action: 'user.login', actor_id: 'alice', occurred_at: 1_700_000_000, outcome: 'success' }],
  count: 1,
  limit: 50,
  offset: 0,
  available_event_types: ['user.login', 'user.logout'],
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
})

describe('AuditEventLogsPanel', () => {
  it('loads the first page on mount and lists the events', async () => {
    queryEventLogs.mockResolvedValue(EVENTS)
    const w = render(AuditEventLogsPanel)
    await flushPromises()

    expect(queryEventLogs).toHaveBeenCalledWith({ user_id: undefined, event_type: undefined, limit: 51, offset: 0 })
    expect(w.text()).toContain('alice')
    expect(w.text()).toContain('user.login')
  })

  it('sends the user filter and returns to the first page when applied', async () => {
    queryEventLogs.mockResolvedValue(EVENTS)
    const w = render(AuditEventLogsPanel)
    await flushPromises()

    await w.find('input').setValue(' bob ')
    await w.findAll('button').find((b) => b.text() === en.audit.eventLogs.refresh)!.trigger('click')
    await flushPromises()

    expect(queryEventLogs).toHaveBeenLastCalledWith({ user_id: 'bob', event_type: undefined, limit: 51, offset: 0 })
  })

  it('shows the empty state when no event matches', async () => {
    queryEventLogs.mockResolvedValue({ ...EVENTS, events: [], count: 0 })
    const w = render(AuditEventLogsPanel)
    await flushPromises()

    expect(w.text()).toContain(en.audit.eventLogs.empty)
  })

  const eventsOf = (n: number) =>
    Array.from({ length: n }, (_, i) => ({ id: `e${i}`, action: 'a', actor_id: `u${i}`, occurred_at: 1_700_000_000, outcome: 'success' }))
  const nextButton = (w: ReturnType<typeof render>) =>
    w.findAll('button').find((b) => b.text() === en.audit.logTable.next)!

  it('offers no next page when the total is an exact multiple of the page size', async () => {
    queryEventLogs.mockResolvedValue({ ...EVENTS, events: eventsOf(50), count: 50 })
    const w = render(AuditEventLogsPanel)
    await flushPromises()

    expect(w.text()).toContain('u49')
    expect(nextButton(w).attributes('disabled')).toBeDefined()
  })

  it('offers a next page and shows only a page when one more row came back', async () => {
    queryEventLogs.mockResolvedValue({ ...EVENTS, events: eventsOf(51), count: 51 })
    const w = render(AuditEventLogsPanel)
    await flushPromises()

    expect(w.text()).toContain('u49')
    expect(w.text()).not.toContain('u50')
    expect(nextButton(w).attributes('disabled')).toBeUndefined()
  })

  it('shows an error with a retry when the call fails', async () => {
    queryEventLogs.mockResolvedValue(null)
    const w = render(AuditEventLogsPanel)
    await flushPromises()

    expect(w.text()).toContain(en.audit.eventLogs.error)
    queryEventLogs.mockResolvedValue(EVENTS)
    await w.findAll('button').find((b) => b.text() === en.audit.eventLogs.retry)!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('alice')
  })

  it('pages with the applied filters, not edits made since (#22214)', async () => {
    queryEventLogs.mockResolvedValue({ ...EVENTS, events: eventsOf(51), count: 51 })
    const w = render(AuditEventLogsPanel)
    await flushPromises()
    await w.find('input').setValue('alice')
    await w.findAll('button').find((b) => b.text() === en.audit.eventLogs.refresh)!.trigger('click')
    await flushPromises()

    await w.find('input').setValue('bob') // edited, never applied
    await nextButton(w).trigger('click')
    await flushPromises()

    expect(queryEventLogs).toHaveBeenLastCalledWith({ user_id: 'alice', event_type: undefined, limit: 51, offset: 50 })
  })

  it('keeps the newest load when an older one finishes last', async () => {
    let releaseOld!: (v: unknown) => void
    queryEventLogs.mockImplementationOnce(() => new Promise((r) => (releaseOld = r)))
    const w = render(AuditEventLogsPanel) // mount load stays pending
    queryEventLogs.mockResolvedValueOnce({ ...EVENTS, events: [{ ...EVENTS.events[0], actor_id: 'newer' }] })
    await w.findAll('button').find((b) => b.text() === en.audit.eventLogs.refresh)!.trigger('click')
    await flushPromises()
    releaseOld({ ...EVENTS, events: [{ ...EVENTS.events[0], actor_id: 'older' }] })
    await flushPromises()

    expect(w.text()).toContain('newer')
    expect(w.text()).not.toContain('older')
  })

  it('reloads the applied view when the Auto-refresh tick changes', async () => {
    queryEventLogs.mockResolvedValue(EVENTS)
    const w = mount(AuditEventLogsPanel, { props: { refreshTick: 0 }, global: { plugins: [i18n] } })
    await flushPromises()
    await w.setProps({ refreshTick: 1 })
    await flushPromises()

    expect(queryEventLogs).toHaveBeenCalledTimes(2)
  })
})

describe('AuditCommandHistoryPanel', () => {
  const HISTORY = [
    { timestamp: '2026-01-01T00:00:00+00:00', user: 'carol', action: 'command.execute', outcome: 'success', details: {} },
  ]

  it('loads on mount with the limit and lists the commands', async () => {
    getCommandHistory.mockResolvedValue(HISTORY)
    const w = render(AuditCommandHistoryPanel)
    await flushPromises()

    expect(getCommandHistory).toHaveBeenCalledWith({ user: undefined, limit: 50 })
    expect(w.text()).toContain('carol')
    expect(w.text()).toContain('command.execute')
  })

  it('formats the timestamp instead of showing the raw ISO text', async () => {
    getCommandHistory.mockResolvedValue(HISTORY)
    const w = render(AuditCommandHistoryPanel)
    await flushPromises()

    expect(w.text()).not.toContain('2026-01-01T00:00:00+00:00')
    expect(w.text()).toContain(formatDateTime(new Date(HISTORY[0].timestamp)))
  })

  it('shows the empty state and the error state', async () => {
    getCommandHistory.mockResolvedValue([])
    const empty = render(AuditCommandHistoryPanel)
    await flushPromises()
    expect(empty.text()).toContain(en.audit.commandHistory.empty)

    getCommandHistory.mockResolvedValue(null)
    const failed = render(AuditCommandHistoryPanel)
    await flushPromises()
    expect(failed.text()).toContain(en.audit.commandHistory.error)
  })

  it('keeps the newest load when an older one finishes last', async () => {
    let releaseOld!: (v: unknown) => void
    getCommandHistory.mockImplementationOnce(() => new Promise((r) => (releaseOld = r)))
    const w = render(AuditCommandHistoryPanel)
    getCommandHistory.mockResolvedValueOnce([{ ...HISTORY[0], user: 'newer' }])
    await w.findAll('button').find((b) => b.text() === en.audit.commandHistory.refresh)!.trigger('click')
    await flushPromises()
    releaseOld([{ ...HISTORY[0], user: 'older' }])
    await flushPromises()

    expect(w.text()).toContain('newer')
    expect(w.text()).not.toContain('older')
  })

  it('reloads when the Auto-refresh tick changes', async () => {
    getCommandHistory.mockResolvedValue(HISTORY)
    const w = mount(AuditCommandHistoryPanel, { props: { refreshTick: 0 }, global: { plugins: [i18n] } })
    await flushPromises()
    await w.setProps({ refreshTick: 1 })
    await flushPromises()

    expect(getCommandHistory).toHaveBeenCalledTimes(2)
  })

  it('reloads with the applied user, not an edit that was never applied (#22212)', async () => {
    getCommandHistory.mockResolvedValue(HISTORY)
    const w = mount(AuditCommandHistoryPanel, { props: { refreshTick: 0 }, global: { plugins: [i18n] } })
    await flushPromises()
    await w.find('input').setValue('carol')
    await w.findAll('button').find((b) => b.text() === en.audit.commandHistory.refresh)!.trigger('click')
    await flushPromises()

    await w.find('input').setValue('mallory') // typed, never applied
    await w.setProps({ refreshTick: 1 })
    await flushPromises()

    expect(getCommandHistory).toHaveBeenLastCalledWith({ user: 'carol', limit: 50 })
  })
})
