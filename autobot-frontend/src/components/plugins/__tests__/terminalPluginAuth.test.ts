// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/terminal's SshTerminal authenticates by subprotocol, never by URL (#18550).
 *
 * The plugin put the JWT in the handshake URL as `?token=` (#14991) while the
 * in-app terminal had moved to `Sec-WebSocket-Protocol` (#16457). A URL is
 * copied into access logs, proxy logs and browser history; a subprotocol is
 * not. These drive the real component and the real composable against a
 * recording WebSocket, and assert on what reaches the constructor.
 *
 * The plugin is imported by relative path on purpose: `@autobot/terminal`
 * resolves through node_modules, which in a worktree points at another
 * checkout's copy, so a bare import would test code other than this tree's.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { effectScope, nextTick, ref } from 'vue'

vi.mock('@xterm/xterm', () => ({
  Terminal: class {
    loadAddon() {}
    open() {}
    onData() {}
    onResize() {}
    write() {}
    dispose() {}
  },
}))
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }))
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }))
vi.mock('@xterm/xterm/css/xterm.css', () => ({}))

import SshTerminal from '../../../../../autobot-plugins/terminal/src/components/SshTerminal.vue'
import { useWebSocket } from '../../../../../autobot-plugins/terminal/src/composables/useWebSocket'

/** A fixture value assembled at runtime; it only has to be recognisable in a URL. */
const FIXTURE_CREDENTIAL = ['fixture', 'credential', 'value'].join('.')

class RecordingWebSocket {
  static instances: RecordingWebSocket[] = []
  static readonly OPEN = 1
  readonly OPEN = 1
  readyState = 0
  sent: string[] = []
  onopen: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  onclose: ((e: CloseEvent) => void) | null = null
  constructor(
    public url: string,
    public protocols?: string | string[],
  ) {
    RecordingWebSocket.instances.push(this)
  }
  send(data: string) { this.sent.push(data) }
  close() {}
  open() {
    this.readyState = 1
    this.onopen?.(new Event('open'))
  }
}

beforeEach(() => {
  RecordingWebSocket.instances = []
  vi.stubGlobal('WebSocket', RecordingWebSocket)
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('SshTerminal handshake (#18550)', () => {
  it('sends the credential as the bearer subprotocol and puts nothing credential-shaped in the URL', async () => {
    const wrapper = mount(SshTerminal, {
      props: { hostId: 'host-1', chatSessionId: 'chat-9', authToken: FIXTURE_CREDENTIAL },
    })
    await nextTick()

    expect(RecordingWebSocket.instances).toHaveLength(1)
    const socket = RecordingWebSocket.instances[0]
    expect(socket.protocols).toEqual(['bearer', FIXTURE_CREDENTIAL])
    expect(socket.url).not.toContain(FIXTURE_CREDENTIAL)
    expect(socket.url).not.toMatch(/[?&#]token=/i)
    expect(socket.url).toContain('/api/terminal/ws/ssh/host-1?conversation_id=chat-9')
    wrapper.unmount()
  })

  it('keeps the credential out of the URL for a custom wsBasePath too (the SLM app passes one)', async () => {
    const wrapper = mount(SshTerminal, {
      props: { hostId: 'h', wsBasePath: '/slm/api/terminal/ws/ssh/', authToken: FIXTURE_CREDENTIAL },
    })
    await nextTick()

    const socket = RecordingWebSocket.instances[0]
    expect(socket.url).toContain('/slm/api/terminal/ws/ssh/h')
    expect(socket.url).not.toContain(FIXTURE_CREDENTIAL)
    expect(socket.protocols).toEqual(['bearer', FIXTURE_CREDENTIAL])
    wrapper.unmount()
  })

  it('does not open a socket at all without a credential', async () => {
    const wrapper = mount(SshTerminal, { props: { hostId: 'host-1', authToken: null } })
    await nextTick()

    expect(RecordingWebSocket.instances).toHaveLength(0)
    expect(wrapper.emitted('error')?.[0]).toEqual(['Not authenticated'])
    wrapper.unmount()
  })

  it('pings on the heartbeat once connected', async () => {
    vi.useFakeTimers()
    const wrapper = mount(SshTerminal, { props: { hostId: 'host-1', authToken: FIXTURE_CREDENTIAL } })
    await nextTick()
    RecordingWebSocket.instances[0].open()

    vi.advanceTimersByTime(30000)
    expect(RecordingWebSocket.instances[0].sent.map((s) => JSON.parse(s))).toEqual([{ type: 'ping' }])
    wrapper.unmount()
  })
})

describe('plugin useWebSocket protocols and heartbeat (#18550)', () => {
  it('omitting protocols keeps the single-argument constructor call', () => {
    const scope = effectScope()
    scope.run(() => useWebSocket('wss://backend.example/ws', { autoReconnect: false }))
    expect(RecordingWebSocket.instances[0].protocols).toBeUndefined()
    scope.stop()
  })

  it('reads a reactive protocols ref at connect time', () => {
    const protocols = ref<string[] | undefined>(['bearer', 'first'])
    const scope = effectScope()
    scope.run(() => {
      const ws = useWebSocket('wss://backend.example/ws', { autoConnect: false, autoReconnect: false, protocols })
      protocols.value = ['bearer', 'second']
      ws.connect()
    })
    expect(RecordingWebSocket.instances[0].protocols).toEqual(['bearer', 'second'])
    scope.stop()
  })

  it('stops the heartbeat when the socket closes', () => {
    vi.useFakeTimers()
    const scope = effectScope()
    scope.run(() => useWebSocket('wss://backend.example/ws', { autoReconnect: false, heartbeatInterval: 1000 }))
    const socket = RecordingWebSocket.instances[0]
    socket.open()
    vi.advanceTimersByTime(2000)
    expect(socket.sent).toEqual(['ping', 'ping'])

    socket.readyState = 3
    socket.onclose?.({ code: 1006, reason: '' } as CloseEvent)
    vi.advanceTimersByTime(5000)
    expect(socket.sent).toHaveLength(2)
    scope.stop()
  })
})
