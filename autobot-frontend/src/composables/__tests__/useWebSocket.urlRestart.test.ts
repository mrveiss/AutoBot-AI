// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The URL watcher restarts only a socket that is not already on the new URL (#21564).
 *
 * A caller that assigns its URL ref and then calls connect() in the same tick has opened the socket
 * to the new URL before the watcher runs; the watcher used to close it and reopen an identical one
 * URL_RESTART_DELAY_MS later. A real change of URL while connected must still reconnect.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { effectScope, nextTick, ref, type EffectScope } from 'vue'
import { useWebSocket, URL_RESTART_DELAY_MS } from '../useWebSocket'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

const URL_ONE = 'wss://backend.example/api/stream/one'
const URL_TWO = 'wss://backend.example/api/stream/two'
const OPEN_DELAY_MS = 10

let scope: EffectScope

describe('useWebSocket URL watcher (#21564)', () => {
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

  it('opens exactly one socket when the url is assigned right before connect()', async () => {
    const url = ref('')
    scope = effectScope()
    const socket = scope.run(() => useWebSocket(url, { autoConnect: false }))!

    url.value = URL_ONE
    socket.connect()
    await nextTick()
    await vi.advanceTimersByTimeAsync(URL_RESTART_DELAY_MS + OPEN_DELAY_MS)

    const instances = MockWebSocket.getAllInstances()
    expect(instances).toHaveLength(1)
    expect(instances[0].url).toBe(URL_ONE)
    expect(instances[0].close).not.toHaveBeenCalled()
    expect(socket.isConnected.value).toBe(true)
  })

  it('still reconnects to the new url when the url changes while connected', async () => {
    const url = ref(URL_ONE)
    scope = effectScope()
    const socket = scope.run(() => useWebSocket(url))!
    await vi.advanceTimersByTimeAsync(OPEN_DELAY_MS)
    expect(socket.isConnected.value).toBe(true)
    const old = MockWebSocket.getLatestInstance()!

    url.value = URL_TWO
    await nextTick()
    expect(old.close).toHaveBeenCalledTimes(1)
    expect(MockWebSocket.getAllInstances()).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(URL_RESTART_DELAY_MS + OPEN_DELAY_MS)

    expect(MockWebSocket.getAllInstances()).toHaveLength(2)
    expect(MockWebSocket.getLatestInstance()!.url).toBe(URL_TWO)
    expect(socket.isConnected.value).toBe(true)
  })

  it('restarts when the url changes again while the socket to the first url is still connecting', async () => {
    const url = ref('')
    scope = effectScope()
    const socket = scope.run(() => useWebSocket(url, { autoConnect: false }))!
    url.value = URL_ONE
    socket.connect()
    await nextTick()

    url.value = URL_TWO
    await nextTick()
    await vi.advanceTimersByTimeAsync(URL_RESTART_DELAY_MS + OPEN_DELAY_MS)

    expect(MockWebSocket.getAllInstances().map((i) => i.url)).toEqual([URL_ONE, URL_TWO])
  })
})
