// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #16744: hosted in a dashboard frame, a registry component shows no title of its own (the
// frame draws it); used standalone, it keeps its title. Both ways, for all four components.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import type { Component } from 'vue'
import en from '@/i18n/locales/en.json'
import AgentActivityVisualization from '../AgentActivityVisualization.vue'
import ResourceHeatmap from '../ResourceHeatmap.vue'
import WorkflowVisualization from '../WorkflowVisualization.vue'
import SystemArchitectureDiagram from '../SystemArchitectureDiagram.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', missingWarn: false, messages: { en } })

// [name, component, its standalone title, a toolbar control that must survive embedding]
const CASES: [string, Component, string, string][] = [
  ['AgentActivityVisualization', AgentActivityVisualization, en.visualizations.agentActivity.defaultTitle, '.view-toggle'],
  ['ResourceHeatmap', ResourceHeatmap, en.visualizations.resourceHeatmap.defaultTitle, '.metric-select'],
  ['WorkflowVisualization', WorkflowVisualization, en.visualizations.workflowViz.defaultTitle, '.layout-btn'],
  ['SystemArchitectureDiagram', SystemArchitectureDiagram, en.visualizations.systemArchitecture.defaultTitle, '.header-actions .action-btn'],
]

async function render(component: Component, embedded: boolean, control: string) {
  const w = mount(component, {
    props: { embedded, autoRefresh: false },
    global: { plugins: [i18n], stubs: { apexchart: true, VueApexCharts: true, Icon: true } },
  })
  await flushPromises()
  const result = { headings: w.findAll('h3').map((h) => h.text().trim()), hasControl: w.find(control).exists() }
  w.unmount()
  return result
}

describe('dashboard registry components: one header (#16744)', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } })))
  })
  afterEach(() => vi.unstubAllGlobals())

  it.each(CASES)('%s hides its own title when embedded, and keeps its controls', async (_name, component, title, control) => {
    const { headings, hasControl } = await render(component, true, control)
    expect(headings).not.toContain(title)
    expect(hasControl).toBe(true)
  })

  it.each(CASES)('%s keeps its own title standalone', async (_name, component, title, control) => {
    const { headings, hasControl } = await render(component, false, control)
    expect(headings).toContain(title)
    expect(hasControl).toBe(true)
  })
})
