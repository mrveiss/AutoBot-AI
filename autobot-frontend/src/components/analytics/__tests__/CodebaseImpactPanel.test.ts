// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * A partial impact result must never render as a complete one (#13506).
 *
 * The engine (#13471) reports `depth_capped` with its un-expanded frontier and
 * an unresolved-edge count precisely so a truncated walk cannot pass for the
 * whole picture — that is the defect #13468 was filed to remove. The endpoint
 * carries those fields; this panel is the last place they can be lost, and
 * losing them here is worse than showing nothing: a partial caller list reads
 * as evidence that nothing else is affected.
 *
 * These tests assert the rendering of that distinction, not the walk.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import CodebaseImpactPanel from '../CodebaseImpactPanel.vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function mountPanel() {
  return mount(CodebaseImpactPanel, {
    global: { plugins: [i18n], stubs: { Icon: true, EmptyState: { props: ['title'], template: '<div class="empty-state">{{ title }}</div>' } } },
  })
}

async function analyze(wrapper: ReturnType<typeof mountPanel>, nodeId = 'pkg.mod.Thing') {
  await wrapper.find('input').setValue(nodeId)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

const COMPLETE = {
  indexed: true,
  root_id: 'pkg.mod.Thing',
  reached: ['a.b', 'c.d'],
  edges: [{ from: 'a.b' }, { from: 'c.d' }],
  skipped_edges: [],
  depth_capped: false,
  depth_capped_frontier: [],
  resolved_edge_count: 2,
  unresolved_edge_count: 0,
  max_depth: 5,
  depth_reached: 2,
}

describe('CodebaseImpactPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('warns that a depth-capped walk is only a lower bound', async () => {
    get.mockResolvedValue({ ...COMPLETE, depth_capped: true, depth_capped_frontier: ['x.y'], depth_reached: 5 })
    const wrapper = mountPanel()

    await analyze(wrapper)

    expect(wrapper.find('.impact-partial').exists()).toBe(true)
    expect(wrapper.text()).toContain('lower bound')
    // The count itself must not read as the final number.
    expect(wrapper.text()).toContain('at least')
  })

  it('warns when edges could not be resolved, even at full depth', async () => {
    get.mockResolvedValue({ ...COMPLETE, skipped_edges: [{ raw: 'helper' }], unresolved_edge_count: 1 })
    const wrapper = mountPanel()

    await analyze(wrapper)

    expect(wrapper.find('.impact-partial').exists()).toBe(true)
    expect(wrapper.text()).toContain('at least')
  })

  it('does not cry wolf on a complete walk', async () => {
    get.mockResolvedValue(COMPLETE)
    const wrapper = mountPanel()

    await analyze(wrapper)

    expect(wrapper.find('.impact-partial').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('at least')
    expect(wrapper.text()).toContain('a.b')
  })

  it('shows both edge counts rather than one derived score', async () => {
    get.mockResolvedValue({ ...COMPLETE, skipped_edges: [{ raw: 'h' }], unresolved_edge_count: 1 })
    const wrapper = mountPanel()

    await analyze(wrapper)

    const text = wrapper.text()
    expect(text).toContain('edges resolved')
    expect(text).toContain('edges unresolved')
    for (const forbidden of ['confidence', 'certainty', '%']) {
      expect(text.toLowerCase()).not.toContain(forbidden)
    }
  })

  it('distinguishes an unbuilt graph from a node with no callers', async () => {
    get.mockResolvedValue({ indexed: false, node_id: 'pkg.mod.Thing', message: 'not available' })
    const wrapper = mountPanel()

    await analyze(wrapper)

    expect(wrapper.find('.empty-state').text()).toContain('Code graph not built')
    expect(wrapper.find('.impact-summary').exists()).toBe(false)
  })

  it('reports no callers as a real answer, not as an error', async () => {
    get.mockResolvedValue({ ...COMPLETE, reached: [], edges: [], resolved_edge_count: 0, depth_reached: 0 })
    const wrapper = mountPanel()

    await analyze(wrapper)

    expect(wrapper.find('.empty-state').text()).toContain('No callers found')
    expect(wrapper.find('.impact-error').exists()).toBe(false)
  })

  it('surfaces a failed request instead of an empty result', async () => {
    get.mockRejectedValue(new Error('boom'))
    const wrapper = mountPanel()

    await analyze(wrapper)

    expect(wrapper.find('.impact-error').exists()).toBe(true)
    expect(wrapper.find('.impact-summary').exists()).toBe(false)
  })

  it('sends the node id to the endpoint', async () => {
    get.mockResolvedValue(COMPLETE)
    const wrapper = mountPanel()

    await analyze(wrapper, 'my.pkg.Widget')

    expect(get).toHaveBeenCalledTimes(1)
    expect(String(get.mock.calls[0][0])).toContain('node_id=my.pkg.Widget')
  })
})
