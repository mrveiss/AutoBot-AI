// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * EntityGraphManager tab-wiring tests — Issue #13474.
 *
 * WHY THIS FILE EXISTS: GraphConnectionPath.vue shipped in review with a full
 * component test suite, 29 translated i18n keys, and no importer anywhere in the
 * app — 653 lines of unreachable Vue. A component test mounts the component
 * directly, so it passes whether or not anything renders it; it can never catch
 * "nobody mounts this". That is the same class of defect #13474 was filed to
 * fix (shortest_path implemented, no caller), reproduced one layer up.
 *
 * These tests assert the wiring itself: the tab exists, and selecting it renders
 * the component.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import EntityGraphManager from './EntityGraphManager.vue'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/knowledge/useKnowledgeEntityGraph', () => ({
  useKnowledgeEntityGraph: () => ({
    graphStats: { entities: 0, relations: 0 },
    graphRagHealth: { status: 'healthy', components: {} },
    isLoadingStats: false,
    statsError: '',
    fetchGraphStats: vi.fn(),
    fetchGraphRagHealth: vi.fn(),
    refreshStats: vi.fn(),
  }),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en: en as Record<string, unknown> },
})

function mountManager() {
  return mount(EntityGraphManager, {
    global: {
      plugins: [i18n],
      stubs: {
        Icon: { template: '<i />', props: ['name'] },
        EntityExtractor: { template: '<div class="stub-extractor" />' },
        GraphRAGQuery: { template: '<div class="stub-query" />' },
        // GraphConnectionPath is deliberately NOT stubbed by name alone — it
        // must actually be registered by the parent for this to resolve.
        GraphConnectionPath: { template: '<div class="stub-connection-path" />' },
      },
    },
  })
}

describe('EntityGraphManager tab wiring (#13474)', () => {
  it('offers a Connection Path tab', () => {
    const wrapper = mountManager()

    const labels = wrapper.findAll('.tab-button').map((b) => b.text())
    expect(labels).toContain(en.knowledge.entityGraph.tabPath)
  })

  it('renders GraphConnectionPath when that tab is selected', async () => {
    const wrapper = mountManager()

    const tab = wrapper
      .findAll('.tab-button')
      .find((b) => b.text().includes(en.knowledge.entityGraph.tabPath))
    expect(tab, 'Connection Path tab button must exist').toBeTruthy()

    await tab!.trigger('click')

    // The component is reachable from the app, not merely importable by a test.
    expect(wrapper.find('.stub-connection-path').exists()).toBe(true)
  })

  it('does not render the connection path on other tabs', () => {
    const wrapper = mountManager()

    // Default tab is 'extract'.
    expect(wrapper.find('.stub-connection-path').exists()).toBe(false)
  })

  it('leaves the pre-existing tabs intact', () => {
    const wrapper = mountManager()

    const labels = wrapper.findAll('.tab-button').map((b) => b.text())
    for (const key of ['tabExtract', 'tabQuery', 'tabStatistics'] as const) {
      expect(labels.some((l) => l.includes(en.knowledge.entityGraph[key]))).toBe(true)
    }
  })
})
