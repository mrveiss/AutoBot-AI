// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * A socket that is no longer the current one leaves the live socket alone (#21530).
 *
 * disconnect() detaches a socket from `ws` but its handlers stay attached, so its close event can
 * arrive after a new connect(). The timers and flags are shared by every socket the composable opens:
 * the stale close used to cancel the new socket's connection timeout and heartbeat, reset its
 * connecting flag and schedule a reconnect of its own. Each case builds that sequence with a new
 * socket whose handshake never completes (a hung attempt) unless it says otherwise.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { effectScope, type EffectScope } from 'vue'
import { useWebSocket, type UseWebSocketOptions } from '../useWebSocket'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

const URL_ONE = 'wss://backend.example/api/stream/one'
const CONNECTION_TIMEOUT_MS = 1000
const HEARTBEAT_MS = 1000
// Past the largest backoff delay (maxReconnectDelay, 10 s).
const PAST_BACKOFF_MS = 60_000
const OPEN_DELAY_MS = 10

let scope: EffectScope

function setup(options: UseWebSocketOptions = {}) {
  scope = effectScope()
  return scope.run(() =>
    useWebSocket(URL_ONE, {
      autoConnect: false,
      connectionTimeout: CONNECTION_TIMEOUT_MS,
      ...options,
    }),
  )!
}

/** connect(), disconnect(), connect(): returns the detached first socket and the second one. */
function replaceSocket(socket: ReturnType<typeof setup>) {
  socket.connect()
  const stale = MockWebSocket.getLatestInstance()!
  socket.disconnect()
  socket.connect()
  const live = MockWebSocket.getLatestInstance()!
  expect(live).not.toBe(stale)
  return { stale, live }
}

describe('useWebSocket when a detached socket reports back (#21530)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.mockImplementation()
    MockWebSocket.clearInstances()
  })

  afterEach(() => {
    scope?.stop()
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    vi.useRealTimers()
  })

  it('keeps the new socket\'s connection timeout and connecting flag', async () => {
    const socket = setup({ autoReconnect: false })
    const { stale, live } = replaceSocket(socket)
    live.cancelPendingOpen() // the new attempt hangs in CONNECTING
    expect(socket.isConnecting.value).toBe(true)

    stale.simulateClose(1000)

    expect(socket.isConnecting.value).toBe(true)
    expect(live.close).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(CONNECTION_TIMEOUT_MS)
    expect(live.close).toHaveBeenCalledTimes(1)
    expect(socket.error.value?.message).toBe('Connection timeout')
  })

  it('keeps the new socket\'s heartbeat', async () => {
    const socket = setup({ autoReconnect: false, heartbeatInterval: HEARTBEAT_MS })
    const { stale, live } = replaceSocket(socket)
    await vi.advanceTimersByTimeAsync(OPEN_DELAY_MS)
    expect(socket.isConnected.value).toBe(true)
    expect(live.send).not.toHaveBeenCalled()

    stale.simulateClose(1000)

    expect(socket.isConnected.value).toBe(true)
    await vi.advanceTimersByTimeAsync(3 * HEARTBEAT_MS + 500)
    expect(live.send).toHaveBeenCalledTimes(3)
    expect(live.send).toHaveBeenCalledWith('ping')
  })

  it('schedules no reconnect for an abnormal close of a detached socket', async () => {
    const socket = setup()
    const { stale, live } = replaceSocket(socket)
    live.cancelPendingOpen()
    expect(MockWebSocket.getAllInstances()).toHaveLength(2)

    stale.simulateClose(1006)
    await vi.advanceTimersByTimeAsync(PAST_BACKOFF_MS)

    expect(MockWebSocket.getAllInstances()).toHaveLength(2)
    expect(socket.reconnectAttempts.value).toBe(0)
  })

  it('does not reset the connecting flag on a detached socket\'s error', () => {
    const onError = vi.fn()
    const socket = setup({ autoReconnect: false, onError })
    const { stale, live } = replaceSocket(socket)
    live.cancelPendingOpen()
    expect(socket.isConnecting.value).toBe(true)

    stale.simulateError()

    expect(socket.isConnecting.value).toBe(true)
    expect(socket.error.value).toBeNull()
    expect(onError).not.toHaveBeenCalled()
  })

  it('still tells the caller that a detached socket closed', () => {
    const onClose = vi.fn()
    const socket = setup({ autoReconnect: false, onClose })
    const { stale } = replaceSocket(socket)

    stale.simulateClose(1000)

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onClose.mock.calls[0][0].code).toBe(1000)
  })

  describe('contrast: the CURRENT socket\'s close', () => {
    it('resets the flags and schedules a reconnect', async () => {
      const socket = setup()
      socket.connect()
      const first = MockWebSocket.getLatestInstance()!
      await vi.advanceTimersByTimeAsync(OPEN_DELAY_MS)
      expect(socket.isConnected.value).toBe(true)

      first.simulateClose(1006)

      expect(socket.isConnected.value).toBe(false)
      expect(socket.isConnecting.value).toBe(false)
      expect(MockWebSocket.getAllInstances()).toHaveLength(1)
      await vi.advanceTimersByTimeAsync(PAST_BACKOFF_MS)
      expect(MockWebSocket.getAllInstances()).toHaveLength(2)
    })

    it('cancels its own connection timeout', async () => {
      const socket = setup({ autoReconnect: false })
      socket.connect()
      const first = MockWebSocket.getLatestInstance()!
      first.cancelPendingOpen()
      expect(socket.isConnecting.value).toBe(true)

      first.simulateClose(1006)

      expect(socket.isConnecting.value).toBe(false)
      await vi.advanceTimersByTimeAsync(CONNECTION_TIMEOUT_MS * 5)
      expect(first.close).not.toHaveBeenCalled()
    })
  })
})
