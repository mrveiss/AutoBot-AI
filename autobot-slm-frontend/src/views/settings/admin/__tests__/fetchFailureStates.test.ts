// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * A failed settings/status fetch stays distinct from defaults (#17971 review):
 * Log Forwarding shows "Unknown" and offers no Start/Stop, and NPU Workers
 * will not save a configuration it never loaded.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import LogForwardingSettings from '../LogForwardingSettings.vue'
import NPUWorkersSettings from '../NPUWorkersSettings.vue'

const api = {
  getLogForwardingStatus: vi.fn(),
  getLogForwardingDestinations: vi.fn(),
  startLogForwarding: vi.fn(),
  stopLogForwarding: vi.fn(),
  getNPUWorkers: vi.fn(),
  getNPULoadBalancingConfig: vi.fn(),
  updateNPULoadBalancingConfig: vi.fn(),
}

function resetApi() {
  for (const fn of Object.values(api)) fn.mockReset()
  api.getLogForwardingDestinations.mockResolvedValue([])
  api.getNPUWorkers.mockResolvedValue([])
}
vi.mock('@/composables/useAutobotApi', () => ({ useAutobotApi: () => api }))

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })
const t = (en as { settings: { admin: Record<string, Record<string, string>> } }).settings.admin

function toggleButton(wrapper: ReturnType<typeof mount>) {
  const label = [t.logForwardingSettings.start, t.logForwardingSettings.stop]
  return wrapper.findAll('button').find((b) => label.includes(b.text().trim()))!
}

describe('Log Forwarding with a failed status fetch', () => {
  beforeEach(resetApi)

  it('shows Unknown and disables Start/Stop rather than claiming "stopped"', async () => {
    api.getLogForwardingStatus.mockRejectedValue(new Error('down'))
    const wrapper = mount(LogForwardingSettings, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.text()).toContain(t.logForwardingSettings.statusUnknown)
    expect(wrapper.text()).not.toContain(t.logForwardingSettings.serviceStopped)
    expect(toggleButton(wrapper).attributes('disabled')).toBeDefined()
  })

  it('enables the action once the status has loaded', async () => {
    api.getLogForwardingStatus.mockResolvedValue({ running: false })
    const wrapper = mount(LogForwardingSettings, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.text()).toContain(t.logForwardingSettings.serviceStopped)
    expect(toggleButton(wrapper).attributes('disabled')).toBeUndefined()
  })
})

describe('NPU Workers with a failed load-balancing fetch', () => {
  beforeEach(resetApi)

  const saveButton = (wrapper: ReturnType<typeof mount>) =>
    wrapper.findAll('button').find((b) => b.text().trim() === t.nPUWorkersSettings.saveConfiguration)!

  it('will not save a configuration it never loaded', async () => {
    api.getNPULoadBalancingConfig.mockRejectedValue(new Error('down'))
    const wrapper = mount(NPUWorkersSettings, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
  })

  it('allows saving once the configuration has loaded', async () => {
    api.getNPULoadBalancingConfig.mockResolvedValue({ strategy: 'round_robin' })
    const wrapper = mount(NPUWorkersSettings, { global: { plugins: [i18n] } })
    await flushPromises()

    expect(saveButton(wrapper).attributes('disabled')).toBeUndefined()
  })
})
