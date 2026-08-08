// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * GraphConnectionPath.vue tests — Issue #13474.
 *
 * The component's job is to make three outcomes visually distinct: a path, "not
 * connected", and "that name does not exist". Asserting they render differently
 * is the whole point — a shared "no results" box would be a regression even
 * though every request still succeeded.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref, readonly } from 'vue'
import GraphConnectionPath from './GraphConnectionPath.vue'
import en from '@/i18n/locales/en.json'

// --- Composable stub -------------------------------------------------------
// The composable has its own tests; here it is a seam so the component can be
// driven through each outcome without HTTP.

const pathResult = ref<Record<string, unknown> | null>(null)
const errorMessage = ref('')
const isFindingPath = ref(false)
const findPath = vi.fn()

vi.mock('@/composables/knowledge/useKnowledgeGraphRAG', () => ({
  useKnowledgeGraphRAG: () => ({
    pathResult,
    errorMessage,
    isFindingPath: readonly(isFindingPath),
    findPath,
  }),
}))

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en: en as Record<string, unknown> },
})

function mountComponent() {
  return mount(GraphConnectionPath, {
    global: {
      plugins: [i18n],
      stubs: { Icon: { template: '<i />', props: ['name'] } },
    },
  })
}

async function submit(wrapper: ReturnType<typeof mountComponent>, from: string, to: string) {
  await wrapper.find('#path-from').setValue(from)
  await wrapper.find('#path-to').setValue(to)
  await wrapper.find('.action-btn.primary').trigger('click')
}

describe('GraphConnectionPath.vue (#13474)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pathResult.value = null
    errorMessage.value = ''
    isFindingPath.value = false
  })

  it('disables submit until both entities are entered', async () => {
    const wrapper = mountComponent()
    const button = wrapper.find('.action-btn.primary')

    expect(button.attributes('disabled')).toBeDefined()

    await wrapper.find('#path-from').setValue('Redis Config')
    expect(button.attributes('disabled')).toBeDefined()

    await wrapper.find('#path-to').setValue('Incident 7')
    expect(button.attributes('disabled')).toBeUndefined()
  })

  it('calls findPath with the documented defaults', async () => {
    const wrapper = mountComponent()

    await submit(wrapper, 'Redis Config', 'Incident 7')

    expect(findPath).toHaveBeenCalledWith({
      from_entity: 'Redis Config',
      to_entity: 'Incident 7',
      relation: null,
      max_depth: 6,
      direction: 'both',
    })
  })

  it('trims entity names before querying', async () => {
    const wrapper = mountComponent()

    await submit(wrapper, '  Redis Config  ', '  Incident 7  ')

    expect(findPath).toHaveBeenCalledWith(
      expect.objectContaining({ from_entity: 'Redis Config', to_entity: 'Incident 7' }),
    )
  })

  it('swaps the two endpoints', async () => {
    const wrapper = mountComponent()
    await wrapper.find('#path-from').setValue('A')
    await wrapper.find('#path-to').setValue('B')

    await wrapper.find('.swap-btn').trigger('click')

    expect((wrapper.find('#path-from').element as HTMLInputElement).value).toBe('B')
    expect((wrapper.find('#path-to').element as HTMLInputElement).value).toBe('A')
  })

  it('renders the chain of nodes and relations for a found path', async () => {
    const wrapper = mountComponent()
    pathResult.value = {
      found: true,
      reason: null,
      from_entity: { id: 'e1', name: 'Redis Config', type: 'decision' },
      to_entity: { id: 'e2', name: 'Incident 7', type: 'incident' },
      missing_entities: [],
      hops: 1,
      path: [
        {
          relation: 'CAUSED',
          direction: 'outgoing',
          edge_id: 'edge-1',
          node: { id: 'e2', name: 'Incident 7', type: 'incident' },
        },
      ],
      traversal_time: 0.004,
    }
    await wrapper.vm.$nextTick()

    const text = wrapper.text()
    expect(wrapper.find('.path-chain').exists()).toBe(true)
    expect(text).toContain('Redis Config')
    expect(text).toContain('Incident 7')
    expect(text).toContain('CAUSED')
    expect(wrapper.findAll('.chain-node')).toHaveLength(2)
  })

  it('marks a backwards-crossed hop distinctly from a forwards one', async () => {
    const wrapper = mountComponent()
    pathResult.value = {
      found: true,
      reason: null,
      from_entity: { id: 'e2', name: 'Incident 7' },
      to_entity: { id: 'e1', name: 'Redis Config' },
      missing_entities: [],
      hops: 1,
      path: [
        {
          relation: 'CAUSED',
          direction: 'incoming',
          node: { id: 'e1', name: 'Redis Config' },
        },
      ],
    }
    await wrapper.vm.$nextTick()

    // Direction is load-bearing: with an undirected search the relation may have
    // been read against the way it is stored, and the UI must not imply
    // otherwise.
    expect(wrapper.find('.chain-edge.incoming').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.knowledge.graphPath.crossedBackwards)
  })

  it('reports a zero-hop result as the same entity, not as an empty path', async () => {
    const wrapper = mountComponent()
    pathResult.value = {
      found: true,
      reason: null,
      from_entity: { id: 'e1', name: 'Redis Config' },
      to_entity: { id: 'e1', name: 'Redis Config' },
      missing_entities: [],
      hops: 0,
      path: [],
    }
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.same-entity-note').exists()).toBe(true)
    expect(wrapper.find('.path-chain').exists()).toBe(false)
  })

  it('shows "no connection" when both entities exist but are unlinked', async () => {
    const wrapper = mountComponent()
    pathResult.value = {
      found: false,
      reason: 'no_path',
      from_entity: { id: 'e1' },
      to_entity: { id: 'e3' },
      missing_entities: [],
      hops: 0,
      path: [],
    }
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.empty-result.no_path').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.knowledge.graphPath.noPathFound)
    expect(wrapper.find('.missing-list').exists()).toBe(false)
  })

  it('names the unresolved entities and does not reuse the "no connection" copy', async () => {
    const wrapper = mountComponent()
    pathResult.value = {
      found: false,
      reason: 'entity_not_found',
      from_entity: null,
      to_entity: null,
      missing_entities: ['Does Not Exist'],
      hops: 0,
      path: [],
    }
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.empty-result.entity_not_found').exists()).toBe(true)
    expect(wrapper.text()).toContain('Does Not Exist')
    // A typo must never read as "these two are unrelated".
    expect(wrapper.text()).not.toContain(en.knowledge.graphPath.noPathFound)
  })

  it('surfaces a transport failure instead of leaving the user with nothing', async () => {
    findPath.mockRejectedValueOnce(new Error('HTTP 500: boom'))
    const wrapper = mountComponent()

    await submit(wrapper, 'A', 'B')
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.error-notification').exists()).toBe(true)
    expect(wrapper.text()).toContain('HTTP 500')
  })

  it('prefers the resolved entity name over the typed one', async () => {
    const wrapper = mountComponent()
    await wrapper.find('#path-from').setValue('redis conf')
    pathResult.value = {
      found: true,
      reason: null,
      // Name lookup is a search, so the match can differ from the input — the
      // user needs to see which entity was actually used.
      from_entity: { id: 'e1', name: 'Redis Config', type: 'decision' },
      to_entity: { id: 'e2', name: 'Incident 7' },
      missing_entities: [],
      hops: 1,
      path: [{ relation: 'CAUSED', direction: 'outgoing', node: { id: 'e2', name: 'Incident 7' } }],
    }
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.chain-node.start').text()).toContain('Redis Config')
  })

  it('distinguishes "not in the graph" from "not connected"', async () => {
    // #13474 review: the entities exist but were never mirrored into the
    // traversal graph. Saying "no connection found" there is a confident wrong
    // answer about data that may well be related.
    const wrapper = mountComponent()
    pathResult.value = {
      found: false,
      reason: 'not_in_graph',
      from_entity: { id: 'e1' },
      to_entity: { id: 'e9' },
      missing_entities: [],
      hops: 0,
      path: [],
    }
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.empty-result.not_in_graph').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.knowledge.graphPath.notInGraph)
    expect(wrapper.text()).not.toContain(en.knowledge.graphPath.noPathFound)
  })

  it('says "1 hop", not "1 hops"', async () => {
    const wrapper = mountComponent()
    pathResult.value = {
      found: true,
      reason: null,
      from_entity: { id: 'e1', name: 'A' },
      to_entity: { id: 'e2', name: 'B' },
      missing_entities: [],
      hops: 1,
      path: [{ relation: 'CAUSED', direction: 'outgoing', node: { id: 'e2', name: 'B' } }],
    }
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Connected in 1 hop')
    expect(wrapper.text()).not.toContain('1 hops')
  })
})
