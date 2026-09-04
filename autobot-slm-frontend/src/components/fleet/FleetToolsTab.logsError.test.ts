// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #15640 — the log viewer must not answer a failed fetch with "No logs available".
 *
 * That string is the user-visible symptom of the defect #15620 fixed. The panel
 * renders `result.value = logs || 'No logs available'`, so as long as
 * `useNodeServices.getLogs()` resolved to `''` on failure, a journal fetch that
 * was cut short by its own ceiling reached the operator as a statement that the
 * node had logged nothing. The composable-level contract is pinned in
 * `composables/useNodeServices.test.ts`; this file pins the sink, because the
 * sink is where the wrong words are actually spoken.
 *
 * The second test is the positive control, and it is not optional: without it
 * "does not render No logs available" would also pass on a panel that had
 * stopped rendering that string in any situation at all, and the assertion
 * would be pinning nothing.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import FleetToolsTab from './FleetToolsTab.vue'
import en from '@/locales/en.json'

const NODE_ID = 'node-alpha'
const SERVICE = 'slm-backend'
const GATEWAY_TIMEOUT_MESSAGE =
  "Journal fetch for 'slm-backend' did not complete within 30s. Any logs it had read are incomplete, not absent."

const h = vi.hoisted(() => ({
  getServiceLogs: vi.fn(),
}))

// Plain arrows rather than `vi.fn`s: the suite runs with `mockReset: true`,
// which strips an implementation registered on a mock before the tests execute.
vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({ getServiceLogs: h.getServiceLogs }),
}))

vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({
    nodeList: [{ node_id: NODE_ID, hostname: 'host-alpha', ip_address: '10.0.0.83', roles: [] }],
  }),
}))

vi.mock('@/utils/ApiClient', () => ({
  slmApiClient: { rawRequest: vi.fn() },
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

interface LogViewerVm {
  activeTool: string | null
  selectedNode: string
  selectedService: string
  result: string | null
  error: string | null
  getServiceLogs: () => Promise<void>
}

/** Mount the panel with the log viewer open and a node/service chosen. */
async function mountLogViewer(): Promise<{ wrapper: ReturnType<typeof mount>; vm: LogViewerVm }> {
  const wrapper = mount(FleetToolsTab, { global: { plugins: [i18n] } })
  const vm = wrapper.vm as unknown as LogViewerVm
  vm.activeTool = 'log-viewer'
  vm.selectedNode = NODE_ID
  vm.selectedService = SERVICE
  await flushPromises()
  return { wrapper, vm }
}

describe('FleetToolsTab log viewer — a failed fetch is not an empty journal', () => {
  it('shows the failure instead of "No logs available" when the fetch is cut short', async () => {
    h.getServiceLogs.mockRejectedValue(new Error(GATEWAY_TIMEOUT_MESSAGE))

    const { wrapper, vm } = await mountLogViewer()
    await vm.getServiceLogs()
    await flushPromises()

    expect(wrapper.text()).not.toContain('No logs available')
    expect(wrapper.text()).toContain('did not complete within')
    expect(vm.result).toBeNull()
    expect(vm.error).toBe(GATEWAY_TIMEOUT_MESSAGE)
  })

  it('still says "No logs available" when the journal really is empty', async () => {
    h.getServiceLogs.mockResolvedValue({
      service_name: SERVICE,
      node_id: NODE_ID,
      logs: '',
      lines_returned: 1,
    })

    const { wrapper, vm } = await mountLogViewer()
    await vm.getServiceLogs()
    await flushPromises()

    expect(wrapper.text()).toContain('No logs available')
    expect(vm.error).toBeNull()
  })

  it('renders the journal when there is one', async () => {
    h.getServiceLogs.mockResolvedValue({
      service_name: SERVICE,
      node_id: NODE_ID,
      logs: 'started in 1.2s\nlistening on the configured port\n',
      lines_returned: 2,
    })

    const { wrapper, vm } = await mountLogViewer()
    await vm.getServiceLogs()
    await flushPromises()

    expect(wrapper.text()).toContain('listening on the configured port')
    expect(wrapper.text()).not.toContain('No logs available')
    expect(vm.error).toBeNull()
  })
})
