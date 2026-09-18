// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useWebSocket's `protocols` option (#16457).
 *
 * `SSHTerminal.vue` never calls `new WebSocket()` itself -- it goes through
 * this composable, which had no way to carry a subprotocol at all. The token
 * travelled in the URL instead (`buildAuthenticatedWsUrl()`), the same
 * exposure #16891 already closed for the two services that construct the
 * socket directly. These tests pin the new option: passed, it reaches the
 * WebSocket constructor's second argument; omitted, every other existing
 * caller of `useWebSocket` keeps today's single-argument `new
 * WebSocket(url)` call, unchanged.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref } from 'vue'
import { useWebSocket } from '../useWebSocket'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

describe('useWebSocket protocols option (#16457)', () => {
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

  it('passes a plain array of protocols to the WebSocket constructor', async () => {
    useWebSocket('wss://backend.example/api/terminal/ws/ssh/host-1', {
      autoReconnect: false,
      protocols: ['bearer', 'fixture-token'],
    })
    await vi.advanceTimersByTimeAsync(20)

    const instance = MockWebSocket.getLatestInstance()
    expect(instance).toBeDefined()
    expect(instance!.protocols).toEqual(['bearer', 'fixture-token'])
  })

  it('reads a reactive protocols ref at connect time', async () => {
    const protocols = ref<string[]>(['bearer', 'fixture-token'])
    useWebSocket('wss://backend.example/api/terminal/ws/ssh/host-1', {
      autoReconnect: false,
      protocols,
    })
    await vi.advanceTimersByTimeAsync(20)

    expect(MockWebSocket.getLatestInstance()!.protocols).toEqual(['bearer', 'fixture-token'])
  })

  it('omitting protocols keeps the unauthenticated single-argument form', async () => {
    useWebSocket('wss://backend.example/api/some/other/endpoint', {
      autoReconnect: false,
    })
    await vi.advanceTimersByTimeAsync(20)

    const instance = MockWebSocket.getLatestInstance()
    expect(instance).toBeDefined()
    expect(instance!.protocols).toBeUndefined()
  })

  it('a later connect() picks up a protocols ref mutated since the first, e.g. a refreshed token', async () => {
    // SSHTerminal.vue's own reconnect flow: wsProtocols.value is reassigned
    // to a fresh buildAuthenticatedWsSubprotocols() result right before each
    // wsConnect() call. A stale closure over the first array would silently
    // keep reconnecting with an expired token.
    const protocols = ref<string[]>(['bearer', 'first-token'])
    const { connect, disconnect } = useWebSocket('wss://backend.example/api/terminal/ws/ssh/host-1', {
      autoConnect: false,
      autoReconnect: false,
      protocols,
    })

    connect()
    await vi.advanceTimersByTimeAsync(20)
    expect(MockWebSocket.getLatestInstance()!.protocols).toEqual(['bearer', 'first-token'])

    disconnect()
    protocols.value = ['bearer', 'second-token']
    connect()
    await vi.advanceTimersByTimeAsync(20)

    const instances = MockWebSocket.getAllInstances()
    expect(instances).toHaveLength(2)
    expect(instances[1].protocols).toEqual(['bearer', 'second-token'])
  })
})
