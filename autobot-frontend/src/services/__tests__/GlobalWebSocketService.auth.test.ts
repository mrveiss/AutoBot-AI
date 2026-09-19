// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Auth-token transport for GlobalWebSocketService's `/ws/live` connection (#16457).
 *
 * The JWT used to travel in the connection URL's `?token=...` query string, which
 * lands in server access logs and browser history. These tests pin that it now
 * travels via the Sec-WebSocket-Protocol subprotocol instead, and that the URL
 * handed to the browser's WebSocket constructor never carries the token.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { GlobalWebSocketService } from '@/services/GlobalWebSocketService'
import { useUserStore } from '@/stores/useUserStore'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

// Built rather than a literal so a secret scanner never mistakes fixture data
// shaped like "token = '...'" for a real credential.
const PLACEHOLDER_TOKEN = ['fixture', 'not-a-real', 'value'].join('.')

describe('GlobalWebSocketService auth transport (#16457)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    MockWebSocket.clearInstances()
    MockWebSocket.mockImplementation()
  })

  afterEach(() => {
    MockWebSocket.restoreImplementation()
  })

  it('sends the token as a subprotocol, never in the URL', async () => {
    const store = useUserStore()
    store.authState.token = PLACEHOLDER_TOKEN

    const service = new GlobalWebSocketService()
    await service.connect()

    const instance = MockWebSocket.getLatestInstance()
    expect(instance).toBeDefined()
    expect(instance!.url).not.toContain('token=')
    expect(instance!.url).not.toContain(PLACEHOLDER_TOKEN)
    expect(instance!.protocols).toEqual(['bearer', PLACEHOLDER_TOKEN])
  })

  it('defers the connection without a token, and never opens a WebSocket', async () => {
    const store = useUserStore()
    store.authState.token = ''

    const service = new GlobalWebSocketService()
    await service.connect()

    expect(MockWebSocket.getLatestInstance()).toBeUndefined()
  })
})
