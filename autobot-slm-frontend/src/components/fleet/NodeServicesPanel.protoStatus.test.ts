// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #17497: a service `status` arrives from the fleet API and from a WebSocket message. An
 * `in` allow-list admitted `Object.prototype` members (`constructor`, `toString`, `__proto__`),
 * so the status tally went NaN. Own-property semantics leave the tally untouched.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

type StatusHandler = (nodeId: string, data: { service_name: string; status: string; success: boolean }) => void

const h = vi.hoisted(() => ({ handler: null as null | ((...a: never[]) => void), getNodeServices: vi.fn() }))

vi.mock('@autobot/ui', () => ({
  BaseAlert: { template: '<div />' },
  PollingPausedAlert: { template: '<div />' },
  formatBytes: (n: number) => String(n),
  formatRelativeTime: () => 'now',
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))
vi.mock('@/components/fleet/ServiceLogsModal.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/composables/useSlmApi', () => ({ useSlmApi: () => ({ getNodeServices: h.getNodeServices }) }))
vi.mock('@/composables/useSlmWebSocket', () => ({
  useSlmWebSocket: () => ({
    connect: vi.fn(),
    subscribe: vi.fn(),
    connected: { value: true },
    onServiceStatus: (fn: (...a: never[]) => void) => { h.handler = fn },
  }),
}))
vi.mock('@/composables/useDashboardPoller', () => ({
  throwUnlessLoaded: vi.fn(),
  useDashboardPoller: (tick: () => Promise<void>) => ({ start: () => tick(), stop: vi.fn() }),
}))
vi.mock('@/i18n', () => ({ default: { global: { t: (k: string) => k } } }))

import NodeServicesPanel from './NodeServicesPanel.vue'

const svc = (name: string, status: string) => ({ service_name: name, status, node_id: 'n1' })

async function mountPanel(services: unknown[]) {
  h.getNodeServices.mockResolvedValue({ services, total: services.length })
  const wrapper = mount(NodeServicesPanel, {
    props: { nodeId: 'n1' },
    global: { mocks: { $t: (k: string) => k }, stubs: { teleport: true } },
  })
  await flushPromises()
  return wrapper
}

/** The running/stopped tally badges are the only elements carrying these two background classes. */
const badge = (w: ReturnType<typeof mount>, cls: string) => w.find(`span.${cls}`).text()

describe('NodeServicesPanel status tally ignores prototype keys (#17497)', () => {
  beforeEach(() => { h.handler = null; h.getNodeServices.mockReset() })

  it.each(['constructor', 'toString', '__proto__', 'hasOwnProperty'])(
    'a fleet-API status of %s does not change the counts',
    async (status) => {
      const wrapper = await mountPanel([svc('a', 'running'), svc('b', status)])
      expect(wrapper.text()).not.toContain('NaN')
      expect(badge(wrapper, 'bg-autobot-pill-ok-bg')).toBe('1')
    },
  )

  it.each(['constructor', 'toString', '__proto__'])(
    'a WebSocket status-update of %s leaves the tally unchanged',
    async (status) => {
      const wrapper = await mountPanel([svc('a', 'running'), svc('b', 'stopped')])
      ;(h.handler as unknown as StatusHandler)('n1', { service_name: 'b', status, success: true })
      await flushPromises()
      expect(wrapper.text()).not.toContain('NaN')
      // b's status is no longer a known one, so it drops out of the tally rather than corrupting it.
      expect(badge(wrapper, 'bg-autobot-bg-tertiary')).toBe('0')
      expect(badge(wrapper, 'bg-autobot-pill-ok-bg')).toBe('1')
    },
  )

  it.each(['constructor', 'toString', '__proto__'])(
    'a row with status %s gets the unknown styling, not an inherited member',
    async (status) => {
      const wrapper = await mountPanel([svc('b', status)])
      const row = wrapper.find('div.bg-autobot-warning-bg')
      expect(row.exists()).toBe(true)
      expect(row.classes()).toContain('text-autobot-pill-warn-fg')
    },
  )
})
