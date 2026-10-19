// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * AgentLedgerMonitor (#18391 AC2): the admin ledger across every company. What
 * the SLM cannot read is said, never shown as empty; an unreadable store is not
 * "nothing there"; the only action is the yield request, and it never removes
 * the claim from the screen.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import AgentLedgerMonitor from './AgentLedgerMonitor.vue'
import en from '@/locales/en.json'
import { jsonResponse, errorResponse } from '@/composables/slmApiClient.testHelper'

const rawRequest = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ slmApiClient: { rawRequest: (...a: unknown[]) => rawRequest(...a) } }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const L = en.monitoring.agentLedger
const BASE = '/monitoring/agent-ledger'

const holder = {
  scope: 'provider:llm', kind: 'provider', agent_id: 'writer', task_id: 'task-1', mode: 'exclusive', intent: 'draft',
  acquired_at: '2026-10-16T10:00:00Z', expires_at: '2026-10-16T11:00:00Z', renewals: 0, company_id: null,
}
const waiter = { ...holder, agent_id: 'reviewer', task_id: 'task-2', position: 1, priority: 0, joined_at: holder.acquired_at }

let routes: Record<string, () => Response>
let wrapper: VueWrapper | undefined

function ok(): Record<string, () => Response> {
  return {
    '/sources': () => jsonResponse({ sources: [
      { source: 'claims', reachable: true, reason: '' },
      { source: 'events', reachable: false, reason: 'down' },
      { source: 'presence', reachable: true, reason: '' },
      { source: 'live_sessions', reachable: true, reason: '' },
      { source: 'peer_messages', reachable: false, reason: 'no snapshot' },
    ] }),
    '/presence': () => jsonResponse({ agents: [
      { kind: 'company_os', tenant_id: 'acme', name: 'writer', busy: true, detail: 'worker', last_seen: 1,
        current_task: { id: 'wi-1', title: 'Draft the Q3 report' } },
      { kind: 'ai_stack', tenant_id: null, name: 'chat', busy: false, detail: null, last_seen: 1, current_task: null },
    ], count: 2 }),
    '/peer-messages': () => jsonResponse({ recipients: [
      { recipient_kind: 'company_os', recipient_name: 'writer', pending: 2, senders: ['a'], oldest_at: 1, tenant_id: 'acme' },
    ], count: 1 }),
    '/idle-subscribers': () => jsonResponse({ subscribers: [], count: 0 }),
    '/contention': () => jsonResponse({ resources: [
      { scope: holder.scope, kind: 'provider', holders: [holder], waiters: [waiter], contended: true },
    ], count: 1 }),
    '/claims': () => jsonResponse({ claims: [holder, { ...holder, scope: 'cpu:gpu0', task_id: 'task-3', company_id: 'acme' }], count: 2 }),
    '/conflicts': () => jsonResponse({ conflicts: [], count: 0 }),
    '/activity': () => jsonResponse({ activity: [], count: 0 }),
    '/dev-loop': () => jsonResponse({ issues: [42], count: 1 }),
    '/dev-loop/42': () => jsonResponse({ issue: 42, actions: [
      { issue: 42, intent: 'fix', outcome: 'refused', estimated_tokens: 1200, reason: 'claim held', at: '2026-10-16T09:00:00Z' },
    ], count: 1 }),
  }
}

/** Mounts the view and opens *tab* ("Now working" is the default tab; most cases here are about another). */
async function mountView(tab: string | null = 'contention'): Promise<VueWrapper> {
  wrapper = mount(AgentLedgerMonitor, { global: { plugins: [i18n] }, attachTo: document.body })
  await flushPromises()
  if (tab) await openTab(wrapper, tab)
  return wrapper
}

async function openTab(w: VueWrapper, id: string): Promise<void> {
  await w.get(`[data-testid="slm-ledger-tab-${id}"]`).trigger('click')
  await flushPromises()
}

beforeEach(() => {
  routes = ok()
  rawRequest.mockReset()
  rawRequest.mockImplementation(async (url: string) => {
    const route = routes[url.slice(BASE.length)]
    return route ? route() : errorResponse(404, { detail: 'unrouted' })
  })
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('AgentLedgerMonitor', () => {
  it('names every source it cannot read right now, and the two known gaps', async () => {
    const w = await mountView(null)
    expect(w.findAll('[data-testid="slm-ledger-down"]').map((d) => d.text()).join(' ')).toContain('ledger activity')
    expect(w.findAll('[data-testid="slm-ledger-down"]').map((d) => d.text()).join(' ')).toContain(L.source.peer_messages)
    expect(w.text()).not.toContain(L.notes.storeDown.replace('{source}', L.source.presence))
    expect(w.find('[data-testid="slm-ledger-gap-16950"]').text()).toBe(L.notes.peerIdentity)
    expect(w.find('[data-testid="slm-ledger-gap-16962"]').text()).toBe(L.notes.busAuth)
  })

  it('says it could not check the sources when /sources fails, rather than listing none', async () => {
    routes['/sources'] = () => errorResponse(500, {})
    const w = await mountView()
    expect(w.find('[data-testid="slm-ledger-sources-unknown"]').exists()).toBe(true)
    expect(w.find('[data-testid="slm-ledger-down"]').exists()).toBe(false)
  })

  it('shows a contended resource with its holder and queue in order', async () => {
    const w = await mountView()
    const card = w.get('[data-testid="slm-ledger-resource"]')
    expect(card.text()).toContain('provider:llm')
    expect(card.text()).toContain('Held by writer (Install-wide)')
    expect(card.text()).toContain('1 waiting')
    expect(card.get('ol').text()).toContain('reviewer — draft')
  })

  it('says it is reading the ledger while a section has not answered yet', async () => {
    rawRequest.mockImplementation(() => new Promise<Response>(() => {}))
    const w = await mountView()
    expect(w.get('[data-testid="ledger-loading"]').text()).toBe(L.state.loading)
    expect(w.find('[data-testid="ledger-empty"]').exists()).toBe(false)
    expect(w.get('[data-testid="slm-ledger-tab-contention"]').text()).toBe(L.tabs.contention)
  })

  it('says nothing is contended only when the ledger was read and holds nothing', async () => {
    routes['/contention'] = () => jsonResponse({ resources: [], count: 0 })
    const w = await mountView()
    expect(w.get('[data-testid="ledger-empty"]').text()).toContain(L.empty.contention)
    expect(w.find('[data-testid="ledger-unavailable"]').exists()).toBe(false)
    expect(w.get('[data-testid="slm-ledger-tab-contention"]').text()).toBe(`${L.tabs.contention} (0)`)
  })

  it('reads an unreachable contention store as unavailable, never as nothing contended', async () => {
    routes['/contention'] = () => errorResponse(503, { error: 'ledger_unavailable', source: 'waitlists', detail: 'x' })
    const w = await mountView()
    expect(w.get('[data-testid="ledger-unavailable"]').text()).toContain('waitlists')
    expect(w.find('[data-testid="ledger-empty"]').exists()).toBe(false)
  })

  it.each([
    ['sent', () => jsonResponse({ token: 'tok' }), L.askState.sent],
    ['too soon', () => errorResponse(429, { detail: 'x' }), L.askState.tooSoon],
    ['not found', () => errorResponse(404, { detail: 'x' }), L.askState.notFound],
    ['unavailable', () => errorResponse(503, { error: 'ledger_unavailable', source: 'claims', detail: 'x' }), L.askState.unavailable],
    ['error', () => errorResponse(500, {}), L.askState.error],
  ])('asks the holder to release and announces %s, keeping the claim held', async (_n, answer, text) => {
    routes['/claims/yield-request'] = answer
    const w = await mountView()
    await w.get('[data-testid="slm-ledger-ask"]').trigger('click')
    await flushPromises()
    expect(rawRequest).toHaveBeenCalledWith(`${BASE}/claims/yield-request`, {
      method: 'POST', body: { scope: 'provider:llm', holder_task_id: 'task-1', reason: '' },
    })
    const status = w.get('[data-testid="slm-ledger-ask-status"]')
    expect(status.attributes('role')).toBe('status')
    expect(status.text()).toBe(text)
    expect(w.get('[data-testid="slm-ledger-ask"]').attributes('aria-describedby')).toBe(status.attributes('id'))
    expect(w.get('[data-testid="slm-ledger-resource"]').text()).toContain('Held by writer')
  })

  it('lists every claim with its company, install-wide when unstamped', async () => {
    const w = await mountView()
    await openTab(w, 'claims')
    const rows = w.get('[data-testid="slm-ledger-claims"]').findAll('tbody tr')
    expect(rows.map((r) => r.findAll('td')[2].text())).toEqual(['Install-wide', 'acme'])
    expect(w.get('[data-testid="slm-ledger-tab-claims"]').text()).toBe('Claims (2)')
  })

  it('reads one issue’s dev-loop history when it is chosen', async () => {
    const w = await mountView()
    await openTab(w, 'devLoop')
    await w.get('[data-testid="slm-ledger-devloop-issue"]').setValue('42')
    await flushPromises()
    expect(rawRequest).toHaveBeenCalledWith(`${BASE}/dev-loop/42`)
    expect(w.get('[data-testid="slm-ledger-devloop-actions"]').text()).toContain('refused')
  })

  it('opens on who is working on what, across every company, with each task and company (#18632)', async () => {
    const w = await mountView(null)
    expect(w.get('[data-testid="slm-ledger-tab-now"]').attributes('aria-selected')).toBe('true')
    const rows = w.get('[data-testid="slm-ledger-presence"]').findAll('tbody tr').map((r) => r.findAll('td').map((c) => c.text()))
    expect(rows).toEqual([
      ['acme', 'writer', 'company_os', L.busy, 'Draft the Q3 report', 'worker'],
      [L.installWide, 'chat', 'ai_stack', L.idle, '', ''],
    ])
    expect(w.get('[data-testid="slm-ledger-peer-messages"]').text()).toContain('(acme)')
    expect(w.get('[data-testid="slm-ledger-peer-messages"]').text()).toContain(L.sentBy.replace('{names}', 'a'))
    expect(w.get('[data-testid="ledger-empty"]').text()).toContain(L.empty.idleSubscribers)
  })

  it('reads a missing live-state snapshot as unavailable, never as nobody working (#18632)', async () => {
    routes['/presence'] = () => errorResponse(503, { error: 'ledger_unavailable', source: 'presence', detail: 'no snapshot' })
    const w = await mountView(null)
    expect(w.get('[data-testid="ledger-unavailable"]').text()).toContain('presence')
    expect(w.find('[data-testid="slm-ledger-presence"]').exists()).toBe(false)
  })

  it('moves between tabs with the arrow keys, wrapping', async () => {
    const w = await mountView(null)
    await w.get('[data-testid="slm-ledger-tab-now"]').trigger('keydown', { key: 'ArrowLeft' })
    await flushPromises()
    const last = w.get('[data-testid="slm-ledger-tab-activity"]')
    expect(last.attributes('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(last.element)
    expect(w.get('[role="tabpanel"]').attributes('aria-labelledby')).toBe('slm-ledger-tab-activity')
  })
})
