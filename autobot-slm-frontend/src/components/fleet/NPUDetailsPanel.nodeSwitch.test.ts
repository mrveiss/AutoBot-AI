// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * NPUDetailsPanel stays mounted between nodes (NPUWorkersTab drives `open`), so a node
 * switch must not show, keep or save the previous node's data (CodeRabbit on #19064):
 * per-node state resets before the fetch, and a late response for an old node is dropped.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { fetchNpuWorkerConfig, fetchNpuNodeMetrics } = vi.hoisted(() => ({
  fetchNpuWorkerConfig: vi.fn(),
  fetchNpuNodeMetrics: vi.fn(),
}))

vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({ fetchNpuWorkerConfig, fetchNpuNodeMetrics }),
}))

// The panel translates its save notice through useI18n; the tests mount without the plugin.
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

import NPUDetailsPanel from './NPUDetailsPanel.vue'

const nodeA = { node_id: 'node-a', hostname: 'npu-a' }
const nodeB = { node_id: 'node-b', hostname: 'npu-b' }

function metrics(inferences: number) {
  return {
    inference_count: inferences,
    avg_latency_ms: 1,
    throughput_rps: 1,
    temperature_celsius: null,
    memory_used_gb: 1,
    memory_total_gb: 2,
    error_count: 0,
  }
}

function config(priority: number) {
  return { priority, weight: 50, max_concurrent: 4, failure_action: 'skip', max_retries: 9, assigned_models: ['m-a'] }
}

/** A promise per node id, resolved by the test when it chooses. */
function deferredByNode() {
  const pending: Record<string, (v: unknown) => void> = {}
  const fn = (id: string) => new Promise((resolve) => { pending[id] = resolve })
  return { fn, resolve: (id: string, v: unknown) => pending[id](v) }
}

function mountPanel(node = nodeA) {
  return mount(NPUDetailsPanel, {
    props: { node: node as never, open: true },
    global: { mocks: { $t: (k: string) => k }, stubs: { teleport: true } },
  })
}

async function openConfig(wrapper: ReturnType<typeof mountPanel>) {
  const toggle = wrapper.findAll('button').find((b) => b.text().includes('workerConfiguration'))
  await toggle!.trigger('click')
}

const priorityValue = (wrapper: ReturnType<typeof mountPanel>) =>
  (wrapper.find('input[type="number"]').element as HTMLInputElement).value

describe('NPUDetailsPanel node switch', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows none of A while B loads', async () => {
    fetchNpuNodeMetrics.mockResolvedValueOnce(metrics(111))
    fetchNpuWorkerConfig.mockResolvedValueOnce(config(7))
    const wrapper = mountPanel()
    await flushPromises()
    await openConfig(wrapper)
    expect(wrapper.text()).toContain('111')
    expect(priorityValue(wrapper)).toBe('7')

    fetchNpuNodeMetrics.mockReturnValueOnce(new Promise(() => {}))
    fetchNpuWorkerConfig.mockReturnValueOnce(new Promise(() => {}))
    await wrapper.setProps({ node: nodeB as never })
    await flushPromises()
    expect(wrapper.text()).not.toContain('111')
    expect(priorityValue(wrapper)).toBe('1')
  })

  it('drops a late A response that lands after switching to B', async () => {
    const m = deferredByNode()
    const c = deferredByNode()
    fetchNpuNodeMetrics.mockImplementation(m.fn)
    fetchNpuWorkerConfig.mockImplementation(c.fn)
    const wrapper = mountPanel()
    await openConfig(wrapper)
    await wrapper.setProps({ node: nodeB as never })

    m.resolve('node-b', metrics(222))
    c.resolve('node-b', config(3))
    await flushPromises()
    m.resolve('node-a', metrics(111))
    c.resolve('node-a', config(7))
    await flushPromises()

    expect(wrapper.text()).toContain('222')
    expect(wrapper.text()).not.toContain('111')
    expect(priorityValue(wrapper)).toBe('3')
  })

  it('resets the form to defaults when B has no config', async () => {
    fetchNpuNodeMetrics.mockResolvedValue(null)
    fetchNpuWorkerConfig.mockResolvedValueOnce(config(7)).mockResolvedValueOnce(null)
    const wrapper = mountPanel()
    await flushPromises()
    await openConfig(wrapper)
    expect(priorityValue(wrapper)).toBe('7')

    await wrapper.setProps({ node: nodeB as never })
    await flushPromises()
    expect(priorityValue(wrapper)).toBe('1')
    expect(wrapper.findAll('input[type="checkbox"]:checked')).toHaveLength(0)
    expect((wrapper.find('select').element as HTMLSelectElement).value).toBe('retry')
  })
})
