// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16245 — RedisServicePanel acts on the node that holds the `redis` role,
 * through the SLM's own node-service API. It used to call the main backend's
 * /redis-service proxy, which fills only `status` and `last_check`, so
 * memory, clients and uptime always rendered empty.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import RedisServicePanel from './RedisServicePanel.vue'
import en from '@/locales/en.json'

const api = vi.hoisted(() => ({
  getNodeServices: vi.fn(),
  startService: vi.fn(),
  stopService: vi.fn(),
  restartService: vi.fn(),
  getServiceLogs: vi.fn(),
}))

vi.mock('@/composables/useSlmApi', () => ({ useSlmApi: () => api }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const text = en.redisServicePanel

const NODE = 'node-redis'
const UNIT = 'redis-stack-server'

function unit(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    node_id: NODE,
    service_name: UNIT,
    status: 'running',
    category: 'system',
    enabled: true,
    active_state: 'active',
    sub_state: 'running',
    main_pid: 4242,
    memory_bytes: 1048576,
    last_checked: '2026-01-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function listing(...services: ReturnType<typeof unit>[]) {
  return { services, total: services.length, page: 1, per_page: 50 }
}

let wrapper: VueWrapper | null = null

function mountPanel(props: { nodeId?: string; serviceName?: string } = { nodeId: NODE, serviceName: UNIT }) {
  wrapper = mount(RedisServicePanel, { props, global: { plugins: [i18n], stubs: { teleport: true } } })
  return wrapper
}

function button(label: string) {
  const found = wrapper!.findAll('button').find((b) => b.text().trim() === label)
  if (!found) throw new Error(`no button labelled ${label}`)
  return found
}

describe('RedisServicePanel on the SLM node-service API (#16245)', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getNodeServices.mockResolvedValue(listing(unit()))
    api.restartService.mockResolvedValue({ action: 'restart', service_name: UNIT, node_id: NODE, success: true, message: '' })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.useRealTimers()
  })

  it('says no node holds the role, asks the SLM nothing, and disables every action', async () => {
    mountPanel({})
    await flushPromises()

    expect(wrapper!.text()).toContain(text.noRedisNode)
    expect(api.getNodeServices).not.toHaveBeenCalled()
    for (const label of [text.start, text.stop, text.restart, text.viewLogs]) {
      expect(button(label).attributes('disabled')).toBeDefined()
    }
  })

  it('reads the exact unit from the node, not a substring match', async () => {
    api.getNodeServices.mockResolvedValue(
      listing(unit({ service_name: 'redis-stack-server-exporter', main_pid: 999 }), unit()),
    )
    mountPanel()
    await flushPromises()

    expect(api.getNodeServices).toHaveBeenCalledWith(NODE, { search: UNIT })
    expect(wrapper!.text()).toContain('4242')
    expect(wrapper!.text()).not.toContain('999')
    expect(wrapper!.text()).toContain('active (running)')
  })

  it('shows values the SLM does not report as unknown', async () => {
    api.getNodeServices.mockResolvedValue(
      listing(unit({ active_state: null, sub_state: null, main_pid: null, memory_bytes: null })),
    )
    mountPanel()
    await flushPromises()

    const unknowns = wrapper!.text().split(text.unknown).length - 1
    expect(unknowns).toBe(3)
  })

  it('says so when the node does not report the unit', async () => {
    api.getNodeServices.mockResolvedValue(listing())
    mountPanel()
    await flushPromises()

    expect(wrapper!.text()).toContain(`${UNIT} is not reported on node ${NODE}.`)
  })

  it('restarts through the node service API and re-reads the status once', async () => {
    mountPanel()
    await flushPromises()
    api.getNodeServices.mockClear()

    await button(text.restart).trigger('click')
    await flushPromises()

    expect(api.restartService).toHaveBeenCalledWith(NODE, UNIT)
    expect(api.getNodeServices).toHaveBeenCalledTimes(1)
  })

  it('shows the SLM message when an action is refused', async () => {
    api.restartService.mockResolvedValue({
      action: 'restart', service_name: UNIT, node_id: NODE, success: false, message: 'unit is masked',
    })
    mountPanel()
    await flushPromises()

    await button(text.restart).trigger('click')
    await flushPromises()

    expect(wrapper!.text()).toContain('unit is masked')
  })

  it('drops the last status instead of showing it as current when a read fails', async () => {
    vi.useFakeTimers()
    mountPanel()
    await flushPromises()
    expect(wrapper!.text()).toContain('4242')

    api.getNodeServices.mockRejectedValue(new Error('offline'))
    await vi.advanceTimersByTimeAsync(10_000)

    expect(wrapper!.text()).not.toContain('4242')
    expect(wrapper!.text()).toContain(text.fetchStatusFailed)
  })

  it('issues exactly one status request per 10s poll tick', async () => {
    vi.useFakeTimers()
    mountPanel()
    await flushPromises()
    api.getNodeServices.mockClear()

    await vi.advanceTimersByTimeAsync(30_000)

    expect(api.getNodeServices).toHaveBeenCalledTimes(3)
  })

  it('reads the unit once the role owner arrives after mount', async () => {
    mountPanel({})
    await flushPromises()

    await wrapper!.setProps({ nodeId: NODE, serviceName: UNIT })
    await flushPromises()

    expect(api.getNodeServices).toHaveBeenCalledWith(NODE, { search: UNIT })
    expect(wrapper!.text()).toContain('4242')
  })

  it('opens the journal for the unit on its node', async () => {
    api.getServiceLogs.mockResolvedValue({ service_name: UNIT, node_id: NODE, logs: 'Ready to accept connections', lines_returned: 1 })
    mountPanel()
    await flushPromises()

    await button(text.viewLogs).trigger('click')
    await flushPromises()

    expect(api.getServiceLogs).toHaveBeenCalledWith(NODE, UNIT, { lines: 100 })
    expect(wrapper!.text()).toContain('Ready to accept connections')
  })
})
