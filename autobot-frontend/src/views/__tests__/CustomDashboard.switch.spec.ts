// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// CustomDashboard.vue: switching dashboards keeps unsaved work (#18242, train-42 review).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent, h, ref } from 'vue'
import en from '@/i18n/locales/en.json'
import type { DashboardLayout } from '@/composables/dashboard/dashboardLayoutModel'

const widget = { id: 'w1', type: 'none', title: 'One', span: 12 as const, height: 320, props: {} }
const layout = ref<DashboardLayout>({ dashboards: [], activeId: null })

// Per-test control of the load state; read when the view mounts, not at hoist time.
const ctl = { loaded: ref(true), retrying: ref(false), load: vi.fn(async (): Promise<void> => undefined) }

vi.mock('@/composables/dashboard/useDashboardLayout', () => ({
  useDashboardLayout: () => ({
    layout, loaded: ctl.loaded, loadError: ref(null), retrying: ctl.retrying,
    load: () => ctl.load(), save: vi.fn(async () => true), reset: vi.fn(),
  }),
}))
vi.mock('@/composables/usePollingJob', () => ({ usePollingJob: () => ({ start: vi.fn(), stop: vi.fn() }) }))
// Widget type 'none' renders no visualization; these stay out of the module graph.
vi.mock('@/components/visualizations/ResourceHeatmap.vue', () => ({ default: {} }))
vi.mock('@/components/visualizations/WorkflowVisualization.vue', () => ({ default: {} }))
vi.mock('@/components/visualizations/AgentActivityVisualization.vue', () => ({ default: {} }))
vi.mock('@/components/visualizations/SystemArchitectureDiagram.vue', () => ({ default: {} }))
// Imported at collection, not inside the first test (see #18833).
import CustomDashboard from '../CustomDashboard.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const Grid = defineComponent({ name: 'DashboardGrid', props: ['widgets'], emits: ['update:widgets'], render: () => h('div') })

async function mountView() {
  const w = mount(CustomDashboard, {
    global: { plugins: [i18n], stubs: { DashboardGrid: Grid, BaseModal: true, Icon: true } },
  })
  await flushPromises()
  return w
}

const saveButton = (w: Awaited<ReturnType<typeof mountView>>) =>
  w.findAll('button').find((b) => b.attributes('aria-label') === en.views.customDashboard.save
    || b.attributes('aria-label') === en.views.customDashboard.saved)!

async function switchTo(w: Awaited<ReturnType<typeof mountView>>, id: string) {
  await w.find('.dashboard-selector select').setValue(id)
  await flushPromises()
}

describe('CustomDashboard dashboard switch', () => {
  beforeEach(() => {
    ctl.loaded.value = true
    ctl.retrying.value = false
    ctl.load = vi.fn(async (): Promise<void> => undefined)
    layout.value = {
      dashboards: [
        { id: 'a', name: 'A', widgets: [widget], createdAt: 0, updatedAt: 0 },
        { id: 'b', name: 'B', widgets: [], createdAt: 0, updatedAt: 0 },
      ],
      activeId: 'a',
    }
  })

  it('keeps an unsaved edit and Save enabled across a switch', async () => {
    const w = await mountView()
    w.findComponent(Grid).vm.$emit('update:widgets', []) // the user removes w1 from A
    await flushPromises()
    await switchTo(w, 'b')
    expect(saveButton(w).attributes('disabled')).toBeUndefined()
    expect(layout.value.dashboards.find((d) => d.id === 'a')!.widgets).toEqual([])
  })

  it('contrast: a switch with nothing unsaved leaves Save disabled and A untouched', async () => {
    const w = await mountView()
    await switchTo(w, 'b')
    expect(saveButton(w).attributes('disabled')).toBeDefined()
    expect(layout.value.dashboards.find((d) => d.id === 'a')!.widgets).toEqual([widget])
  })

  it('shows the defaults read-only with a status line while the load is pending, then the saved layout', async () => {
    let finish: () => void = () => undefined
    ctl.loaded.value = false
    ctl.retrying.value = true
    ctl.load = vi.fn(() => new Promise<void>((resolve) => { finish = resolve }))
    layout.value = { dashboards: [{ id: 'a', name: 'A', widgets: [widget], createdAt: 0, updatedAt: 0 }], activeId: 'a' }
    const w = await mountView()
    expect((w.findComponent(Grid).props('widgets') as { id: string }[]).map((x) => x.id)).toEqual(['w1'])
    expect(w.find('[data-test="layout-retrying"]').exists()).toBe(true)
    expect(w.find('.dashboard-selector .icon-btn').attributes('disabled')).toBeDefined()
    expect(w.find('.empty-dashboard').exists()).toBe(false)
    // saved layout arrives: the composable swaps `layout`, then load() resolves
    layout.value = { dashboards: [{ id: 'a', name: 'A', widgets: [{ ...widget, id: 'saved' }], createdAt: 0, updatedAt: 0 }], activeId: 'a' }
    ctl.loaded.value = true
    ctl.retrying.value = false
    finish()
    await flushPromises()
    expect((w.findComponent(Grid).props('widgets') as { id: string }[]).map((x) => x.id)).toEqual(['saved'])
    expect(w.find('[data-test="layout-retrying"]').exists()).toBe(false)
    expect(w.find('.dashboard-selector .icon-btn').attributes('disabled')).toBeUndefined()
  })

  it('hides the add-first-widget button while the layout is not loaded', async () => {
    ctl.loaded.value = false
    layout.value = { dashboards: [{ id: 'b', name: 'B', widgets: [], createdAt: 0, updatedAt: 0 }], activeId: 'b' }
    ctl.load = vi.fn(() => new Promise<void>(() => undefined))
    const w = await mountView()
    expect(w.find('.empty-dashboard').exists()).toBe(true)
    expect(w.find('.empty-dashboard button').exists()).toBe(false)
  })
})
