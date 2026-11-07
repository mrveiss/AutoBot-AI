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

vi.mock('@/composables/dashboard/useDashboardLayout', () => ({
  useDashboardLayout: () => ({
    layout, loaded: ref(true), loadError: ref(null),
    load: vi.fn(async () => undefined), save: vi.fn(async () => true), reset: vi.fn(),
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
})
