// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'

/**
 * The terminal's host selector is the SLM node registry's answer (#15227).
 *
 * It used to be `getHosts()` — a literal array of seven VMs in
 * `config/ssot-config.ts`. Asserting "the selector has options" passed against
 * that array, which is why the issue calls it out: the test that matters is
 * that an **empty registry produces an empty selector**, because a static
 * array cannot do that.
 */

interface FakeNode {
  node_id: string
  hostname: string
  ip_address: string
  roles?: string[]
}

const nodes = ref<FakeNode[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const fetchNodes = vi.fn(async () => {})

vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({
    get nodeList() {
      return nodes.value
    },
    get isLoading() {
      return isLoading.value
    },
    get error() {
      return error.value
    },
    fetchNodes,
  }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('@autobot/terminal', () => ({
  SshTerminal: { name: 'SshTerminal', props: ['hostId', 'wsBasePath', 'authToken'], template: '<div />' },
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountTool() {
  const TerminalTool = (await import('./TerminalTool.vue')).default
  const wrapper = mount(TerminalTool, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

function optionLabels(wrapper: Awaited<ReturnType<typeof mountTool>>): string[] {
  return wrapper.findAll('option').map(o => o.text())
}

describe('TerminalTool host selector', () => {
  beforeEach(() => {
    nodes.value = []
    isLoading.value = false
    error.value = null
    fetchNodes.mockClear()
  })

  it('asks the SLM for the node list on mount', async () => {
    await mountTool()
    expect(fetchNodes).toHaveBeenCalledTimes(1)
  })

  it('offers exactly the nodes the registry reports', async () => {
    nodes.value = [
      { node_id: 'node-eight', hostname: 'node-eight', ip_address: '10.77.4.21', roles: ['worker'] },
      { node_id: 'node-nine', hostname: 'node-nine', ip_address: '10.77.4.22', roles: [] },
    ]
    const wrapper = await mountTool()
    expect(optionLabels(wrapper)).toEqual(['node-eight (10.77.4.21)', 'node-nine (10.77.4.22)'])
  })

  it('shows a node the fleet gains, and drops one it loses, with no code change', async () => {
    nodes.value = [{ node_id: 'node-eight', hostname: 'node-eight', ip_address: '10.77.4.21' }]
    const wrapper = await mountTool()
    expect(optionLabels(wrapper)).toHaveLength(1)

    nodes.value = [
      { node_id: 'node-eight', hostname: 'node-eight', ip_address: '10.77.4.21' },
      { node_id: 'node-ten', hostname: 'node-ten', ip_address: '10.77.4.23' },
    ]
    await flushPromises()
    expect(optionLabels(wrapper)).toEqual(['node-eight (10.77.4.21)', 'node-ten (10.77.4.23)'])

    nodes.value = [{ node_id: 'node-ten', hostname: 'node-ten', ip_address: '10.77.4.23' }]
    await flushPromises()
    expect(optionLabels(wrapper)).toEqual(['node-ten (10.77.4.23)'])
  })

  it('offers nothing when the registry reports no nodes', async () => {
    // The test a static array cannot pass: with seven hardcoded hosts this
    // selector had seven options no matter what the fleet contained.
    const wrapper = await mountTool()
    expect(optionLabels(wrapper)).toEqual([])
    expect(wrapper.text()).toContain(en.tools.admin.terminalTool.noNodesEnrolled)
  })

  it('says the registry is unreachable rather than showing an empty fleet', async () => {
    error.value = 'Network Error'
    const wrapper = await mountTool()
    expect(wrapper.text()).toContain(en.tools.admin.terminalTool.nodeListUnavailable)
    expect(wrapper.text()).not.toContain(en.tools.admin.terminalTool.noNodesEnrolled)
  })

  it('labels a list left over from an earlier read as stale, not current', async () => {
    nodes.value = [{ node_id: 'node-eight', hostname: 'node-eight', ip_address: '10.77.4.21' }]
    error.value = 'Network Error'
    const wrapper = await mountTool()
    expect(wrapper.text()).toContain(en.tools.admin.terminalTool.nodeListStale)
  })

  it('retries the fetch on demand', async () => {
    error.value = 'Network Error'
    const wrapper = await mountTool()
    await wrapper.find('button').trigger('click')
    expect(fetchNodes).toHaveBeenCalledTimes(2)
  })

  it('selects the first node without inventing one when there are none', async () => {
    const empty = await mountTool()
    expect(empty.findComponent({ name: 'SshTerminal' }).exists()).toBe(false)

    nodes.value = [{ node_id: 'node-eight', hostname: 'node-eight', ip_address: '10.77.4.21' }]
    await flushPromises()
    expect(empty.findComponent({ name: 'SshTerminal' }).props('hostId')).toBe('node-eight')
  })
})

describe('the static host array is gone, not merely unused', () => {
  it('ssot-config exports no host list for this page to fall back to', async () => {
    const ssot = await import('@/config/ssot-config')
    expect('getHosts' in ssot).toBe(false)
    expect('hosts' in ssot.getConfig()).toBe(false)
  })
})
