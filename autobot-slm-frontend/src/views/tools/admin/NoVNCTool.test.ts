// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #22144: the SLM noVNC tool connects for real to a selected FLEET endpoint.
 * The websocket the API returned is opened (no fake timer), the client link is
 * derived from that URL, and nothing outside the fleet endpoint list is offered.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import NoVNCTool from './NoVNCTool.vue'
import en from '@/locales/en.json'
import { probeVncWebsocket, vncClientUrlFromWebsocket } from '@/config/vnc-client'

const WS_URL = 'wss://203.0.113.7:6080/websockify'

const getVncEndpoints = vi.fn()
vi.mock('@/composables/useSlmApi', () => ({
  useSlmApi: () => ({ getVncEndpoints }),
}))

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

class FakeSocket {
  static instances: FakeSocket[] = []
  static outcome: 'open' | 'error' = 'open'
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) {
    FakeSocket.instances.push(this)
    queueMicrotask(() => (FakeSocket.outcome === 'open' ? this.onopen?.() : this.onerror?.()))
  }
}

function endpointsResponse() {
  return {
    endpoints: [
      { credential_id: 'c1', node_id: 'n1', hostname: 'fleet-a', ip_address: '203.0.113.7', vnc_type: 'desktop', name: null, port: 6080, websocket_url: WS_URL, is_active: true },
    ],
    total: 1,
  }
}

async function mountTool() {
  const wrapper = mount(NoVNCTool, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('NoVNCTool (SLM)', () => {
  beforeEach(() => {
    FakeSocket.instances = []
    FakeSocket.outcome = 'open'
    getVncEndpoints.mockReset().mockResolvedValue(endpointsResponse())
    vi.stubGlobal('WebSocket', FakeSocket)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('offers only the fleet endpoints the SLM API returned', async () => {
    const wrapper = await mountTool()
    const options = wrapper.findAll('select option')
    expect(options).toHaveLength(1)
    expect(options[0].text()).toContain('203.0.113.7')
  })

  it('Connect opens the endpoint websocket for real, then reports connected', async () => {
    const wrapper = await mountTool()
    await wrapper.find('button.px-4').trigger('click')
    await flushPromises()
    expect(FakeSocket.instances.map((s) => s.url)).toEqual([WS_URL])
    expect(wrapper.text()).toContain('Connected')
    expect(wrapper.find('iframe').attributes('src')).toBe('https://203.0.113.7:6080/vnc.html?autoconnect=true&resize=scale')
  })

  it('a failed websocket is an error, never a fake success', async () => {
    FakeSocket.outcome = 'error'
    const wrapper = await mountTool()
    await wrapper.find('button.px-4').trigger('click')
    await flushPromises()
    expect(wrapper.find('iframe').exists()).toBe(false)
    expect(wrapper.text()).toContain("Could not connect to fleet-a")
  })
})

describe('vnc-client helpers', () => {
  it('derives the client link scheme and authority from the endpoint websocket_url', () => {
    expect(vncClientUrlFromWebsocket('wss://h:6080/websockify')).toMatch(/^https:\/\/h:6080\/vnc\.html\?/)
    expect(vncClientUrlFromWebsocket('ws://h:6080/websockify')).toMatch(/^http:\/\/h:6080\//)
    expect(() => vncClientUrlFromWebsocket('ftp://h/x')).toThrow()
  })

  it('probeVncWebsocket rejects on timeout instead of resolving', async () => {
    const never = () => ({ close: vi.fn(), onopen: null, onerror: null }) as unknown as WebSocket
    await expect(probeVncWebsocket('wss://h/x', 10, never)).rejects.toThrow('timeout')
  })
})
