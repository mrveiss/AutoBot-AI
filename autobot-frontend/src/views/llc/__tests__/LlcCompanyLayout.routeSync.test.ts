// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21511: browser back/forward between two companies changes only the route's :companyId. The route
// guard runs when the company routes are entered, not on a param-only change, so the company store --
// which supplies the organisation header of every request -- stayed on the company that was left, and
// a view scoped by that header (the agent ledger) showed the wrong company. The layout now writes the
// URL's company into the store before the keyed view remounts.
//
// A real router with the real guard on the parent record (as in production), the real layout, the real
// pinia store and the real ledger view. Only the HTTP layer is replaced; each ledger request records
// the company `decorateHeaders` would read at that moment (`getSelectedCompanyId`, the same read).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView, type Router } from 'vue-router'
import { h } from 'vue'
import en from '@/i18n/locales/en.json'

const { rawRequest } = vi.hoisted(() => ({ rawRequest: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: { rawRequest } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({
    get: () => Promise.resolve([{ id: 'c1', name: 'Alpha' }, { id: 'c2', name: 'Bravo' }]),
  }),
}))
vi.mock('@/composables/useEventBus', () => ({ useEventBus: () => ({ subscribe: () => () => undefined }) }))
vi.mock('@/composables/useNotificationBus', () => ({
  useNotificationBus: () => ({ notifyInfo: vi.fn(), notifyWarning: vi.fn(), notifyError: vi.fn() }),
}))
vi.mock('@/components/llc/LlcSidebar.vue', () => ({
  default: { name: 'LlcSidebar', render: () => null },
}))
vi.mock('@/components/llc/workflowPlanner/PlanFirstProcessCard.vue', () => ({
  default: { name: 'PlanFirstProcessCard', render: () => null },
}))

import LlcCompanyLayout from '../LlcCompanyLayout.vue'
import AgentLedgerView from '../AgentLedgerView.vue'
import { llcCompanyParamGuard } from '@/router/llcGuards'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import { getSelectedCompanyId } from '@/utils/orgContext'
import { useUiMode } from '@/composables/useUiMode'

const LEDGER_PATH = '/coordination/ledger/'
const FIELD: Record<string, string> = {
  presence: 'agents', claims: 'claims', waitlists: 'waiters', conflicts: 'conflicts',
  activity: 'activity', 'peer-messages': 'recipients', 'idle-subscribers': 'subscribers',
}

/** One recorded ledger request: what was asked and which company the header would have named. */
interface Recorded {
  section: string
  company: string
}
const recorded: Recorded[] = []

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function buildRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/llc/companies', name: 'llc-company-select', component: { render: () => null } },
      {
        path: '/llc/companies/:companyId',
        component: LlcCompanyLayout,
        beforeEnter: llcCompanyParamGuard,
        children: [{ path: 'ledger', name: 'llc-ledger', component: AgentLedgerView }],
      },
    ],
  })
}

/** Run `action` and resolve once the navigation it starts has finished (back/forward return nothing). */
async function navigated(router: Router, action: () => unknown): Promise<void> {
  const done = new Promise<void>((resolve) => {
    const remove = router.afterEach(() => {
      remove()
      resolve()
    })
  })
  action()
  await done
  await flushPromises()
}

let router: Router
let wrapper: VueWrapper

beforeEach(async () => {
  recorded.length = 0
  rawRequest.mockImplementation(async (url: string) => {
    const section = url.split(LEDGER_PATH)[1]
    // Read at call time, as ApiClient.decorateHeaders does for the organisation header.
    recorded.push({ section, company: getSelectedCompanyId() })
    return { status: 200, ok: true, json: async () => ({ [FIELD[section]]: [], count: 0 }) }
  })
  const pinia = createPinia()
  setActivePinia(pinia)
  useUiMode().setMode('minimal')
  // The list holds both companies: a list that did not would make the store drop the selection.
  await useLlcCompanyStore().fetchCompanies()
  router = buildRouter()
  await router.push({ name: 'llc-ledger', params: { companyId: 'c1' } })
  await router.isReady()
  wrapper = mount({ render: () => h(RouterView) }, { global: { plugins: [pinia, router, i18n] } })
  await flushPromises()
})

afterEach(() => {
  wrapper.unmount()
})

const companiesOf = (from: number): string[] => recorded.slice(from).map((r) => r.company)

describe('the company layout keeps the company store on the route\'s company (#21511)', () => {
  it('sends the ledger requests of the company the route names, also after back and forward', async () => {
    const store = useLlcCompanyStore()
    expect(recorded.length).toBeGreaterThan(0)
    expect(new Set(companiesOf(0))).toEqual(new Set(['c1']))

    // What the sidebar's company select does: select, then push the same route for the new company.
    let mark = recorded.length
    store.selectCompany('c2')
    await navigated(router, () => router.push({ name: 'llc-ledger', params: { companyId: 'c2' } }))
    expect(recorded.length).toBeGreaterThan(mark)
    expect(new Set(companiesOf(mark))).toEqual(new Set(['c2']))

    mark = recorded.length
    await navigated(router, () => router.back())
    expect(router.currentRoute.value.params.companyId).toBe('c1')
    expect(store.selectedCompanyId).toBe('c1')
    expect(recorded.length).toBeGreaterThan(mark)
    expect(new Set(companiesOf(mark))).toEqual(new Set(['c1']))

    mark = recorded.length
    await navigated(router, () => router.forward())
    expect(router.currentRoute.value.params.companyId).toBe('c2')
    expect(store.selectedCompanyId).toBe('c2')
    expect(recorded.length).toBeGreaterThan(mark)
    expect(new Set(companiesOf(mark))).toEqual(new Set(['c2']))
  })

  it('leaves the store alone when a param-only push names no company', async () => {
    const store = useLlcCompanyStore()
    expect(store.selectedCompanyId).toBe('c1')

    // A param-only change never runs the parent's beforeEnter guard, so the placeholder reaches the layout.
    await navigated(router, () => router.push('/llc/companies/undefined/ledger'))

    expect(router.currentRoute.value.params.companyId).toBe('undefined')
    expect(store.selectedCompanyId).toBe('c1')
  })
})
