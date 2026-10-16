// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #18391 on screen: an unreadable ledger says "couldn't read the ledger" and
 * names the store -- never the empty "No claims" -- and an empty one says the
 * opposite (AC3). "Ask holder to release" is present but disabled until its
 * route lands (#18599), with its reason exposed to assistive tech. Activity is
 * a Full-mode tab, as in the mockup.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { rawRequest } = vi.hoisted(() => ({ rawRequest: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: { rawRequest } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))

import AgentLedgerView from '../AgentLedgerView.vue'
import { useUiMode } from '@/composables/useUiMode'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const L = en.llc.ledger

const json = (status: number, body: unknown) => ({ status, ok: status < 400, json: async () => body })
const FIELD: Record<string, string> = {
  presence: 'agents', claims: 'claims', waitlists: 'waiters', conflicts: 'conflicts',
  activity: 'activity', 'peer-messages': 'recipients', 'idle-subscribers': 'subscribers',
}
const CLAIM = {
  scope: 'provider:openai', kind: 'provider', agent_id: 'research-agent', task_id: 't1', mode: 'exclusive',
  intent: 'summarise', acquired_at: '2026-10-16T10:00:00Z', expires_at: '2026-10-16T11:00:00Z', renewals: 1, company_id: 'c1',
}

function serve(routes: Record<string, ReturnType<typeof json>>) {
  rawRequest.mockImplementation(async (url: string) => {
    const name = url.split('/coordination/ledger/')[1]
    return routes[name] ?? json(200, { [FIELD[name]]: [], count: 0 })
  })
}

async function mountOn(tab: string) {
  const w = mount(AgentLedgerView, { global: { plugins: [i18n] } })
  await flushPromises()
  await w.get(`[data-testid="ledger-tab-${tab}"]`).trigger('click')
  return w
}

describe('AgentLedgerView (#18391)', () => {
  beforeEach(() => {
    rawRequest.mockReset()
    useUiMode().setMode('minimal')
  })

  it('an unreadable claims store reads "couldn\'t read the ledger", naming it -- not "no claims"', async () => {
    serve({ claims: json(503, { error: 'ledger_unavailable', source: 'claims', detail: 'redis down' }) })
    const w = await mountOn('claims')
    const alert = w.get('[data-testid="ledger-unavailable"]')
    expect(alert.text()).toContain(L.state.unavailableTitle)
    expect(alert.text()).toContain(L.state.unavailableBody.replace('{source}', 'claims'))
    expect(w.text()).not.toContain(L.empty.claims)
  })

  it('an empty claims list reads "no claims" -- not "couldn\'t read"', async () => {
    serve({})
    const w = await mountOn('claims')
    expect(w.get('[data-testid="ledger-empty"]').text()).toContain(L.empty.claims)
    expect(w.find('[data-testid="ledger-unavailable"]').exists()).toBe(false)
  })

  it('lists claims once read, and counts them on the tab', async () => {
    serve({ claims: json(200, { claims: [CLAIM], count: 1 }) })
    const w = await mountOn('claims')
    expect(w.get('[data-testid="ledger-claims"]').text()).toContain('provider:openai')
    expect(w.get('[data-testid="ledger-tab-claims"]').text()).toBe(`${L.tabs.claims} (1)`)
  })

  it('offers "Ask holder to release" for a held scope, disabled, with its reason linked', async () => {
    serve({ claims: json(200, { claims: [CLAIM], count: 1 }) })
    const w = await mountOn('contention')
    const ask = w.get('[data-testid="ledger-ask"]')
    // aria-disabled, not disabled: still a Tab stop, so its linked reason is reachable.
    expect(ask.attributes('aria-disabled')).toBe('true')
    expect(ask.attributes('disabled')).toBeUndefined()
    await ask.trigger('click')
    expect(rawRequest.mock.calls.every(([, init]) => (init as { method: string }).method === 'GET')).toBe(true)
    expect(ask.text()).toBe(L.ask)
    const why = w.get(`#${ask.attributes('aria-describedby')}`)
    expect(why.text()).toBe(L.askUnavailable)
  })

  it('tabs follow WAI-ARIA: one Tab stop, arrows and Home/End move selection and focus, panels are wired', async () => {
    serve({})
    const w = mount(AgentLedgerView, { global: { plugins: [i18n] }, attachTo: document.body })
    await flushPromises()
    const tab = (id: string) => w.get(`[data-testid="ledger-tab-${id}"]`)
    expect(w.findAll('[role="tab"]').map((t) => t.attributes('tabindex'))).toEqual(['0', '-1', '-1'])

    await tab('now').trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(tab('claims').attributes('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(tab('claims').element)
    const panel = w.get('[role="tabpanel"]')
    expect(panel.attributes('id')).toBe(tab('claims').attributes('aria-controls'))
    expect(panel.attributes('aria-labelledby')).toBe(tab('claims').attributes('id'))

    await tab('claims').trigger('keydown', { key: 'End' })
    await flushPromises()
    expect(tab('contention').attributes('aria-selected')).toBe('true')
    await tab('contention').trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(tab('now').attributes('aria-selected')).toBe('true') // wraps
    await tab('now').trigger('keydown', { key: 'Home' })
    expect(tab('now').attributes('tabindex')).toBe('0')
    w.unmount()
  })

  it('shows Activity only in Full mode', async () => {
    serve({})
    const w = mount(AgentLedgerView, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.find('[data-testid="ledger-tab-activity"]').exists()).toBe(false)
    useUiMode().setMode('full')
    await flushPromises()
    expect(w.find('[data-testid="ledger-tab-activity"]').exists()).toBe(true)
  })
})
