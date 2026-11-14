// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21512: the sidebar's company select kept the old company's portfolio and program ids in the URL it
// pushed (only board routes were redirected), so the new company showed "not found" for them. The real
// sidebar on a real router built from the production company routes: only the HTTP client, the live
// event feed and the routed views are replaced.

import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, type RouteRecordRaw, type Router } from 'vue-router'
import en from '@/i18n/locales/en.json'

vi.mock('@/views/WorkflowBuilderView.vue', () => ({ default: { render: () => null } }))
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get: () => Promise.resolve([]) }) }))
vi.mock('@/composables/useLiveEvents', () => ({ useLiveEvents: () => ({ subscribe: () => () => undefined }) }))

import LlcSidebar from '../LlcSidebar.vue'
import { llcCompanyChildren } from '@/router/llcRoutes'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'

const Stub = { render: () => null }

/** The production company records with their lazy views swapped for a stub; redirects are kept. */
function stubbed(records: RouteRecordRaw[]): RouteRecordRaw[] {
  return records.map((record) => {
    const { component: _view, props: _props, children, ...rest } = record as RouteRecordRaw & { children?: RouteRecordRaw[] }
    const copy = { ...rest, ...(record.redirect === undefined ? { component: Stub } : {}) }
    return (children ? { ...copy, children: stubbed(children) } : copy) as RouteRecordRaw
  })
}

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

let router: Router

async function mountOn(name: string, params: Record<string, string>) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useLlcCompanyStore()
  store.companies = [{ id: 'c1', name: 'Alpha' }, { id: 'c2', name: 'Bravo' }]
  store.selectCompany('c1')
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/llc/companies', name: 'llc-company-select', component: Stub },
      { path: '/llc/companies/:companyId', component: Stub, children: stubbed(llcCompanyChildren) },
    ],
  })
  await router.push({ name, params: { companyId: 'c1', ...params } })
  await router.isReady()
  const wrapper = mount(LlcSidebar, { global: { plugins: [pinia, router, i18n] } })
  await flushPromises()
  return wrapper
}

async function switchToBravo(wrapper: Awaited<ReturnType<typeof mountOn>>) {
  await wrapper.get('#llc-company-select').setValue('c2')
  await flushPromises()
}

const current = () => ({ name: router.currentRoute.value.name, params: router.currentRoute.value.params })

describe('the sidebar company switch (#21512)', () => {
  it.each([
    ['llc-programs', { portfolioId: 'p1' }],
    ['llc-projects', { programId: 'pr1' }],
  ])('leaves %s for the new company\'s portfolios, without the old company\'s id', async (name, params) => {
    const wrapper = await mountOn(name, params)
    expect(current().name).toBe(name)

    await switchToBravo(wrapper)

    expect(current()).toEqual({ name: 'llc-portfolios', params: { companyId: 'c2' } })
    wrapper.unmount()
  })

  it('still leaves a board for the new company\'s backlog', async () => {
    const wrapper = await mountOn('llc-kanban-board', { boardId: 'b1' })
    expect(current().name).toBe('llc-kanban-board')

    await switchToBravo(wrapper)

    expect(current()).toEqual({ name: 'llc-backlog', params: { companyId: 'c2' } })
    wrapper.unmount()
  })

  it('keeps a route that carries no id of the old company', async () => {
    const wrapper = await mountOn('llc-ledger', {})
    expect(current().params).toEqual({ companyId: 'c1' })

    await switchToBravo(wrapper)

    expect(current()).toEqual({ name: 'llc-ledger', params: { companyId: 'c2' } })
    wrapper.unmount()
  })
})
