// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #22144: the main-app VNC plugin's toolbar sends the selected host as `host_id` (the backend refuses a
 * control without one), and offers no controls while no host is selected.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import VncPlugin from '../VncPlugin.vue'

const host = { id: 'h-secret', name: 'box', host: 'h.example.test', port: 6080, url: 'https://h.example.test:6080/vnc.html' }
const stubs = { VncViewer: true }

describe('VncPlugin controls', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('sends the selected host id with a control request', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ status: 'success', image_data: 'AA==' }) }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(VncPlugin, { props: { modelValue: true, host, apiBaseUrl: '/api' }, global: { stubs } })
    await wrapper.find('button[title="Take Screenshot"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect((fetchMock.mock.calls[0] as unknown[])[0]).toBe('/api/vnc/screenshot?host_id=h-secret')
  })

  it('renders no controls while no host is selected, so no request can go out without a host_id', () => {
    const wrapper = mount(VncPlugin, { props: { modelValue: true, apiBaseUrl: '/api' }, global: { stubs } })
    expect(wrapper.find('button[title="Take Screenshot"]').exists()).toBe(false)
  })
})
