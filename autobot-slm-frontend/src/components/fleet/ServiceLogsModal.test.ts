// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #16245 — ServiceLogsModal, extracted from NodeServicesPanel so the Redis
 * panel shows the same journal view.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ServiceLogsModal from './ServiceLogsModal.vue'
import en from '@/locales/en.json'

const api = vi.hoisted(() => ({ getServiceLogs: vi.fn() }))

vi.mock('@/composables/useSlmApi', () => ({ useSlmApi: () => api }))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })
const text = en.fleet.serviceLogsModal

function mountModal(serviceName: string | null) {
  return mount(ServiceLogsModal, {
    props: { nodeId: 'node-a', serviceName },
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
}

describe('ServiceLogsModal (#16245)', () => {
  beforeEach(() => {
    api.getServiceLogs.mockReset()
  })

  it('renders nothing and fetches nothing while no service is set', async () => {
    const wrapper = mountModal(null)
    await flushPromises()

    expect(wrapper.text()).toBe('')
    expect(api.getServiceLogs).not.toHaveBeenCalled()
  })

  it('fetches the tail for the service when it opens and shows it', async () => {
    api.getServiceLogs.mockResolvedValue({ service_name: 'nginx', node_id: 'node-a', logs: 'started', lines_returned: 1 })
    const wrapper = mountModal('nginx')
    await flushPromises()

    expect(api.getServiceLogs).toHaveBeenCalledWith('node-a', 'nginx', { lines: 100 })
    expect(wrapper.text()).toContain('Logs: nginx')
    expect(wrapper.text()).toContain('started')
  })

  it('says the logs could not be loaded rather than showing an empty tail', async () => {
    api.getServiceLogs.mockRejectedValue(new Error('504'))
    const wrapper = mountModal('nginx')
    await flushPromises()

    expect(wrapper.text()).toContain(text.loadFailed)
  })

  it('refetches when reopened for another service', async () => {
    api.getServiceLogs.mockResolvedValue({ service_name: 'x', node_id: 'node-a', logs: '', lines_returned: 0 })
    const wrapper = mountModal('nginx')
    await flushPromises()
    await wrapper.setProps({ serviceName: null })
    await wrapper.setProps({ serviceName: 'redis-stack-server' })
    await flushPromises()

    expect(api.getServiceLogs).toHaveBeenLastCalledWith('node-a', 'redis-stack-server', { lines: 100 })
  })

  it('emits close from the close button', async () => {
    api.getServiceLogs.mockResolvedValue({ service_name: 'nginx', node_id: 'node-a', logs: '', lines_returned: 0 })
    const wrapper = mountModal('nginx')
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text().trim() === text.close)!.trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
