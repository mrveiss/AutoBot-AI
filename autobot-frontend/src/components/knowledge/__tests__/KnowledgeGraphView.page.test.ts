// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** #19727: /knowledge/graph draws the graph, or says why there isn't one; it is never blank. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import KnowledgeGraphView from '../KnowledgeGraphView.vue'

const entities = ref<unknown[]>([])
const relations = ref<unknown[]>([])
const sources = ref<unknown[]>([])
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
vi.mock('@/composables/useKnowledgeGraph', () => ({
  useKnowledgeGraph: () => ({ stats: { entityCount: 0, eventCount: 0, summaryCount: 0 } }),
}))
vi.mock('@/composables/knowledge/useKnowledgeGraphEntities', () => ({
  useKnowledgeGraphEntities: () => ({
    entities,
    relations,
    isLoading: ref(false),
    errorMessage: ref(''),
    sources,
    fetchGraphData: vi.fn().mockResolvedValue(undefined),
    createGraphEntity: vi.fn(),
  }),
}))
vi.mock('@/composables/charts/useCytoscapeLibrary', () => ({
  useCytoscapeLibrary: (onReady: () => void) => ({
    loading: ref(false),
    error: ref(null),
    cytoscapeModule: ref(() => fakeCy),
    ensureReady: async () => onReady(),
    retry: vi.fn(),
  }),
}))

function page() {
  return mount(KnowledgeGraphView, {
    global: {
      mocks: { $t: (key: string) => key },
      stubs: { RouterLink: true, RouterView: true, Icon: true, MemoryOrphanManager: true },
    },
  })
}

describe('KnowledgeGraphView at /knowledge/graph', () => {
  beforeEach(() => {
    added.length = 0
    relations.value = []
  })

  it('draws a node for each entity', async () => {
    sources.value = [{ key: 'memory', ok: true, count: 3 }]
    entities.value = ['a', 'b', 'c'].map((id) => ({ id, name: id, type: 'concept', observations: [] }))
    page()
    await flushPromises()
    expect(added.filter((element) => !element.data.source).map((element) => element.data.id)).toEqual(['a', 'b', 'c'])
  })

  it('says the KB is empty rather than showing a blank canvas', async () => {
    sources.value = [{ key: 'memory', ok: true, count: 0 }]
    entities.value = []
    const wrapper = page()
    await flushPromises()
    expect(wrapper.find('.empty-state').text()).toContain('knowledge.graph.noEntitiesFound')
  })

  it('says a store could not be read rather than that it is empty', async () => {
    sources.value = [{ key: 'memory', ok: false, count: 0, error: 'down' }]
    entities.value = []
    const wrapper = page()
    await flushPromises()
    expect(wrapper.find('.empty-state').text()).toContain('knowledge.graph.sourcesUnreadable')
  })
})
