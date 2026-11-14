// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * SSHTerminal reports its connection state only for the live socket (#21548).
 *
 * The real useWebSocket runs against the shared MockWebSocket. disconnect() detaches the socket, so
 * that socket's later close is stale: it must not flip the state of a reconnect in progress nor emit
 * a second `disconnected`, while disconnect() itself still reports once.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { MockWebSocket } from '../../../test/mocks/websocket-mock'
import SSHTerminal from '../SSHTerminal.vue'

vi.mock('@xterm/xterm', () => ({
  Terminal: vi.fn(function (this: Record<string, unknown>) {
    this.loadAddon = vi.fn()
    this.open = vi.fn()
    this.onData = vi.fn()
    this.onResize = vi.fn()
    this.dispose = vi.fn()
    this.write = vi.fn()
  }),
}))

vi.mock('@xterm/addon-fit', () => ({
  FitAddon: vi.fn(function (this: Record<string, unknown>) {
    this.fit = vi.fn()
  }),
}))

vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: vi.fn() }))

vi.mock('@/utils/buildAuthenticatedWsUrl', () => ({
  buildAuthenticatedWsSubprotocols: vi.fn(),
}))

vi.mock('@/composables/usePollingJob', () => ({
  usePollingJob: vi.fn(),
}))

import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { buildAuthenticatedWsSubprotocols } from '@/utils/buildAuthenticatedWsUrl'
import { usePollingJob } from '@/composables/usePollingJob'

const OPEN_DELAY_MS = 10
// useWebSocket restarts a socket that is opened in the same tick as its URL changes: connect()
// sets wsUrl ('' -> url) and calls wsConnect(), the URL watcher then disconnects that first socket
// and reconnects after this delay (useWebSocket.ts scheduleRestart). The live socket is the second one.
const URL_RESTART_MS = 100

let wrapper: VueWrapper | null

function mountTerminal() {
  wrapper = mount(SSHTerminal, {
    props: { hostId: 'host-1' },
    global: { stubs: { Icon: true } },
  })
  return wrapper
}

/** Let the mount-time connect settle: the watcher restart, then the live socket's open. */
async function settleConnection(view: VueWrapper) {
  await vi.advanceTimersByTimeAsync(URL_RESTART_MS + OPEN_DELAY_MS)
  await view.vm.$nextTick()
}

const barClasses = () => wrapper!.find('.connection-bar').classes()
const disconnectedEmits = () => wrapper!.emitted('disconnected') ?? []

describe('SSHTerminal when a detached socket closes (#21548)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.mockImplementation()
    MockWebSocket.clearInstances()
    vi.mocked(Terminal).mockImplementation(function (this: Record<string, unknown>) {
      this.loadAddon = vi.fn()
      this.open = vi.fn()
      this.onData = vi.fn()
      this.onResize = vi.fn()
      this.dispose = vi.fn()
      this.write = vi.fn()
    } as unknown as () => Terminal)
    vi.mocked(FitAddon).mockImplementation(function (this: Record<string, unknown>) {
      this.fit = vi.fn()
    } as unknown as () => FitAddon)
    vi.mocked(buildAuthenticatedWsSubprotocols).mockReturnValue(['bearer'])
    vi.mocked(usePollingJob).mockReturnValue({
      start: vi.fn(),
      stop: vi.fn(),
    } as unknown as ReturnType<typeof usePollingJob>)
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    vi.useRealTimers()
  })

  it('ignores the stale close while a new connection is being made', async () => {
    const view = mountTerminal()
    await settleConnection(view)
    expect(barClasses()).toContain('connected')
    const first = MockWebSocket.getLatestInstance()!

    ;(view.vm as unknown as { disconnect: () => void }).disconnect()
    ;(view.vm as unknown as { connect: () => void }).connect()
    const second = MockWebSocket.getLatestInstance()!
    second.cancelPendingOpen() // the new attempt hangs in CONNECTING
    await view.vm.$nextTick()
    expect(second).not.toBe(first)
    expect(barClasses()).toContain('connecting')
    expect(disconnectedEmits()).toHaveLength(1)

    first.simulateClose(1000)
    await view.vm.$nextTick()

    expect(barClasses()).toContain('connecting')
    expect(barClasses()).not.toContain('disconnected')
    expect(disconnectedEmits()).toHaveLength(1)
  })

  it('emits disconnected exactly once for a deliberate disconnect, close event included', async () => {
    const view = mountTerminal()
    await settleConnection(view)
    const first = MockWebSocket.getLatestInstance()!

    ;(view.vm as unknown as { disconnect: () => void }).disconnect()
    await view.vm.$nextTick()
    expect(barClasses()).toContain('disconnected')
    expect(disconnectedEmits()).toHaveLength(1)

    first.simulateClose(1000)
    await view.vm.$nextTick()

    expect(disconnectedEmits()).toHaveLength(1)
  })

  it('still reports the live socket\'s own close', async () => {
    const view = mountTerminal()
    await settleConnection(view)
    const live = MockWebSocket.getLatestInstance()!
    expect(disconnectedEmits()).toHaveLength(0)

    live.simulateClose(1006)
    await view.vm.$nextTick()

    expect(barClasses()).toContain('disconnected')
    expect(disconnectedEmits()).toHaveLength(1)
  })
})
