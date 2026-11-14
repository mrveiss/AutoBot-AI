// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** #20945: loading the next facts page keeps the canvas mounted, and the new entities reach the graph. */
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import KnowledgeGraphView from '../KnowledgeGraphView.vue'
import apiClient from '@/utils/ApiClient'

const added: Array<{ data: { id: string; source?: string } }> = []
const fakeCy = {
  on: vi.fn(),
  add: (elements: typeof added) => added.push(...elements),
  elements: () => ({ remove: vi.fn() }),
  layout: () => ({ run: vi.fn(), on: vi.fn() }),
  fit: vi.fn(),
  destroy: vi.fn(),
  nodes: () => ({ length: 0, forEach: vi.fn() }),
  edges: () => ({ length: 0, forEach: vi.fn() }),
}

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/knowledge/graph' }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/i18n', () => ({ default: { global: { t: (key: string) => key } } }))
vi.mock('@/utils/ApiClient', () => ({ default: { get: vi.fn(), post: vi.fn(), call: vi.fn() } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@/composables/useKnowledgeGraph', () => ({
  useKnowledgeGraph: () => ({ stats: { entityCount: 0, eventCount: 0, summaryCount: 0 } }),
}))
vi.mock('@/composables/charts/useCytoscapeLibrary', async () => {
  const { ref } = await import('vue')
  return {
    useCytoscapeLibrary: (onReady: () => void) => ({
      loading: ref(false),
      error: ref(null),
      cytoscapeModule: ref(() => fakeCy),
      ensureReady: async () => onReady(),
      retry: vi.fn(),
    }),
  }
})

const entity = (id: string) => ({ id, name: id, type: 'concept', observations: [] })
const graphPage = (ids: string[], cursor: string | null) => ({
  data: { entities: ids.map(entity), relations: [] },
  stats: { sections: [{ key: 'facts', cursor }] },
})

describe('KnowledgeGraphView load more', () => {
  it('keeps the canvas container mounted while the next page loads and draws its entities', async () => {
    vi.mocked(apiClient.get).mockImplementation((async (url: string) =>
      url.includes('/memory/entities/all') ? { data: { entities: [] } } : graphPage(['a'], '100:0')) as never)
    let release: (value: unknown) => void = () => undefined
    vi.mocked(apiClient.call).mockImplementation((() => new Promise((resolve) => { release = resolve })) as never)
    const wrapper = mount(KnowledgeGraphView, {
      global: {
        mocks: { $t: (key: string) => key },
        stubs: { RouterLink: true, RouterView: true, Icon: true, MemoryOrphanManager: true },
      },
    })
    await flushPromises()
    const container = wrapper.find('.cytoscape-container').element
    await wrapper.find('.error-notification[role="status"] button').trigger('click')
    expect(wrapper.find('.loading-state').exists()).toBe(false)
    expect(wrapper.find('.cytoscape-container').element).toBe(container)
    release(graphPage(['b'], null))
    await flushPromises()
    expect(wrapper.find('.cytoscape-container').element).toBe(container)
    expect(added.filter((element) => !element.data.source).map((element) => element.data.id)).toContain('b')
  })

  it('offers the continuation when the first scan window is empty but carries a cursor', async () => {
    vi.mocked(apiClient.get).mockImplementation((async (url: string) =>
      url.includes('/memory/entities/all') ? { data: { entities: [] } } : graphPage([], '100:0')) as never)
    vi.mocked(apiClient.call).mockResolvedValue(graphPage(['b'], null) as never)
    const wrapper = mount(KnowledgeGraphView, {
      global: {
        mocks: { $t: (key: string) => key },
        stubs: { RouterLink: true, RouterView: true, Icon: true, MemoryOrphanManager: true },
      },
    })
    await flushPromises()
    const more = wrapper.find('.error-notification[role="status"] button')
    expect(more.exists()).toBe(true)
    await more.trigger('click')
    await flushPromises()
    expect(apiClient.call).toHaveBeenCalled()
    expect(wrapper.find('.error-notification[role="status"] button').exists()).toBe(false)
  })
})
