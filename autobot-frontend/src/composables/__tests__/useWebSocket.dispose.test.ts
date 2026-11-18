// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * A useWebSocket whose owner is gone stays closed (#21516).
 *
 * `reconnect()` and the URL watcher restart the socket 100 ms after closing the old one, and a socket
 * closed while CONNECTING reports 1006 and schedules a backoff reconnect. None of these timers were
 * cancelled when the owning scope was disposed, so a socket could open after its component was gone
 * and nothing would ever close it. The contrast cases pin the other half: a live scope still
 * restarts, even when the OLD socket's close event arrives after `reconnect()`, and a manual
 * disconnect() followed by connect() still connects.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { useWebSocket } from '../useWebSocket'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

const URL_ONE = 'wss://backend.example/api/stream/one'
const URL_TWO = 'wss://backend.example/api/stream/two'
// Past the 100 ms restart and past the largest backoff delay (maxReconnectDelay, 10 s).
const PAST_BACKOFF_MS = 60_000

describe('useWebSocket after its owner is disposed (#21516)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.mockImplementation()
    MockWebSocket.clearInstances()
  })

  afterEach(() => {
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    vi.useRealTimers()
  })

  it('does not restart a pending reconnect() once the scope is stopped', async () => {
    const scope = effectScope()
    const socket = scope.run(() => useWebSocket(URL_ONE))!
    expect(MockWebSocket.getAllInstances()).toHaveLength(1)

    socket.reconnect()
    scope.stop()
    await vi.advanceTimersByTimeAsync(200)

    expect(MockWebSocket.getAllInstances()).toHaveLength(1)
  })

  it('does not restart the URL watcher reconnect once the scope is stopped', async () => {
    const url = ref(URL_ONE)
    const scope = effectScope()
    scope.run(() => useWebSocket(url))
    expect(MockWebSocket.getAllInstances()).toHaveLength(1)

    url.value = URL_TWO
    await nextTick()
    scope.stop()
    await vi.advanceTimersByTimeAsync(200)

    expect(MockWebSocket.getAllInstances()).toHaveLength(1)
  })

  it('refuses connect() after the scope is stopped', () => {
    const scope = effectScope()
    const socket = scope.run(() => useWebSocket(URL_ONE))!
    scope.stop()

    socket.connect()

    expect(MockWebSocket.getAllInstances()).toHaveLength(1)
  })

  it('does not schedule a backoff reconnect when a socket disposed while CONNECTING closes with 1006', async () => {
    const scope = effectScope()
    scope.run(() => useWebSocket(URL_ONE))
    const first = MockWebSocket.getLatestInstance()!
    expect(first.readyState).toBe(MockWebSocket.CONNECTING)

    scope.stop()
    first.simulateClose(1006)
    await vi.advanceTimersByTimeAsync(PAST_BACKOFF_MS)

    expect(MockWebSocket.getAllInstances()).toHaveLength(1)
  })

  it('restarts a live scope even when the old socket close event arrives after reconnect()', async () => {
    const scope = effectScope()
    const socket = scope.run(() => useWebSocket(URL_ONE))!
    const old = MockWebSocket.getLatestInstance()!

    socket.reconnect()
    // The old socket's onclose stays attached and calls clearTimers(); it must not cancel the restart.
    old.simulateClose(1000)
    await vi.advanceTimersByTimeAsync(200)

    expect(MockWebSocket.getAllInstances()).toHaveLength(2)
    scope.stop()
  })

  it('connects after a manual disconnect() when no scope was disposed', async () => {
    const scope = effectScope()
    const socket = scope.run(() => useWebSocket(URL_ONE))!
    await vi.advanceTimersByTimeAsync(20)
    expect(socket.isConnected.value).toBe(true)

    socket.disconnect()
    expect(socket.isConnected.value).toBe(false)
    socket.connect()

    expect(MockWebSocket.getAllInstances()).toHaveLength(2)
    scope.stop()
  })
})
