// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// CompanyDashboard.vue layout persistence (#18242, #18968 review): the view restores a stored
// layout, saves through withCompanyWidgets, keeps unsaved work on a failed PUT, and offers no
// working Save before the layout has loaded. The real useDashboardLayout runs against a mocked
// ApiClient, so the PUT/GET path is the one the page uses.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import en from '@/i18n/locales/en.json'
import { COMPANY_OS_DASHBOARD_ID, COMPANY_WIDGET_TYPES, type CompanyWidget } from '@/composables/dashboard/companyOsDashboard'

const http = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), delete: vi.fn() }))
const llcGet = vi.hoisted(() => vi.fn())
vi.mock('@/utils/ApiClient', () => ({ default: http }))
vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: llcGet, post: vi.fn() }),
}))
vi.mock('@/composables/llc/useLlcCompanyContext', () => ({ useLlcCompanyContext: () => ({ resolveCompanyId: async () => 'c1' }) }))
vi.mock('@/composables/useLiveEvents', () => ({ useLiveEvents: () => ({ subscribe: vi.fn() }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: async () => true }) }))
// Imported at collection, not inside the first test (see #18833).
import CompanyDashboard from '../CompanyDashboard.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })
const Grid = defineComponent({ name: 'DashboardGrid', props: ['widgets', 'editing'], emits: ['update:widgets'], render: () => h('div') })
const K = en.views.customDashboard

const storedWidgets = (): CompanyWidget[] =>
  [...COMPANY_WIDGET_TYPES].reverse().map((type) => ({ id: type, type, title: '', span: 4, height: 200, props: {} }))

function storedResponse(widgets = storedWidgets()) {
  return { data: { layout: { dashboards: [{ id: COMPANY_OS_DASHBOARD_ID, name: 'x', widgets, createdAt: 0, updatedAt: 0 }], activeId: COMPANY_OS_DASHBOARD_ID } } }
}

async function mountView() {
  const w = mount(CompanyDashboard, { global: { plugins: [i18n], stubs: { DashboardGrid: Grid, CompanyDashboardWidget: true } } })
  await flushPromises()
  return w
}

const button = (w: Awaited<ReturnType<typeof mountView>>, text: string) => w.findAll('button').find((b) => b.text() === text)
const gridWidgets = (w: Awaited<ReturnType<typeof mountView>>) => w.findComponent(Grid).props('widgets') as CompanyWidget[]

async function edit(w: Awaited<ReturnType<typeof mountView>>) {
  const moved = [...gridWidgets(w)].reverse()
  w.findComponent(Grid).vm.$emit('update:widgets', moved)
  await flushPromises()
  return moved
}

describe('CompanyDashboard layout', () => {
  beforeEach(() => {
    http.get.mockReset().mockResolvedValue(storedResponse())
    http.put.mockReset().mockResolvedValue({})
    http.delete.mockReset().mockResolvedValue({})
    llcGet.mockReset().mockImplementation(async (url: string) => (url.includes('/activity') ? { items: [] } : []))
  })

  it('restores the stored layout on load', async () => {
    const w = await mountView()
    expect(http.get).toHaveBeenCalledWith(expect.stringContaining('/users/me/dashboard-layouts/company-os'))
    expect(gridWidgets(w).map((x) => x.type)).toEqual([...COMPANY_WIDGET_TYPES].reverse())
  })

  it('saves the edited widgets as the page dashboard (withCompanyWidgets)', async () => {
    const w = await mountView()
    const moved = await edit(w)
    await button(w, K.save)!.trigger('click')
    await flushPromises()
    const [, body] = http.put.mock.calls[0]
    expect(body.activeId).toBe(COMPANY_OS_DASHBOARD_ID)
    expect(body.dashboards).toHaveLength(1)
    expect(body.dashboards[0].widgets).toEqual(moved)
    expect(button(w, K.save)).toBeUndefined() // clean again
  })

  it('keeps the unsaved edit and shows the save error when the PUT fails', async () => {
    http.put.mockRejectedValue(new Error('503'))
    const w = await mountView()
    const moved = await edit(w)
    await button(w, K.save)!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain(K.saveFailed)
    expect(button(w, K.save)).toBeDefined() // still dirty
    expect(gridWidgets(w)).toEqual(moved)
  })

  it('stays dirty when the user edits again while the save is in flight', async () => {
    let resolvePut: (v: unknown) => void = () => {}
    http.put.mockReturnValue(new Promise((r) => { resolvePut = r }))
    const w = await mountView()
    await edit(w)
    await button(w, K.save)!.trigger('click')
    const later = await edit(w) // lands while the PUT is pending
    resolvePut({})
    await flushPromises()
    expect(http.put).toHaveBeenCalledTimes(1)
    expect(button(w, K.save)).toBeDefined() // the later edit is still unsaved
    expect(gridWidgets(w)).toEqual(later)
  })

  it('offers no working Edit or Save until the layout has loaded', async () => {
    http.get.mockReturnValue(new Promise(() => {})) // load never settles
    const w = await mountView()
    expect(button(w, K.editLayout)!.attributes('disabled')).toBeDefined()
    await edit(w)
    expect(button(w, K.save)!.attributes('disabled')).toBeDefined()
  })

  it('contrast: once loaded, Edit is enabled', async () => {
    const w = await mountView()
    expect(button(w, K.editLayout)!.attributes('disabled')).toBeUndefined()
  })
  it('keeps the grid mounted while company data loads, so an edit session survives a refetch', async () => {
    llcGet.mockReturnValue(new Promise(() => {})) // the data fetch never settles
    const w = await mountView()
    expect(w.find('[role="status"]').text()).toBe(en.llc.dashboard.loading)
    expect(w.findComponent(Grid).exists()).toBe(true)
  })
})
