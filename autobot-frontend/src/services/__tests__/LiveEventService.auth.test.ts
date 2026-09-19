// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Auth-token transport for LiveEventService's `/ws/live` connection (#16457).
 *
 * `LiveEventService` connects to the same `/ws/live` endpoint as
 * `GlobalWebSocketService` (see `GlobalWebSocketService.auth.test.ts`), but had
 * been left on the URL `?token=...` fallback during #16891's review — the JWT
 * still landed in server access logs and browser history for this client. These
 * tests pin that it now travels via the Sec-WebSocket-Protocol subprotocol
 * instead, and that the URL handed to the browser's WebSocket constructor never
 * carries the token.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { LiveEventService } from '@/services/LiveEventService'
import { useUserStore } from '@/stores/useUserStore'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

// Built rather than a literal so a secret scanner never mistakes fixture data
// shaped like "token = '...'" for a real credential.
const PLACEHOLDER_TOKEN = ['fixture', 'not-a-real', 'value'].join('.')

describe('LiveEventService auth transport (#16457)', () => {
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

    const service = new LiveEventService()
    await service.connect()

    const instance = MockWebSocket.getLatestInstance()
    expect(instance).toBeDefined()
    expect(instance!.url).not.toContain('token=')
    expect(instance!.url).not.toContain(PLACEHOLDER_TOKEN)
    expect(instance!.protocols).toEqual(['bearer', PLACEHOLDER_TOKEN])
  })

  it('an explicit token argument is also sent as a subprotocol, never in the URL', async () => {
    const service = new LiveEventService()
    await service.connect(PLACEHOLDER_TOKEN)

    const instance = MockWebSocket.getLatestInstance()
    expect(instance).toBeDefined()
    expect(instance!.url).not.toContain('token=')
    expect(instance!.url).not.toContain(PLACEHOLDER_TOKEN)
    expect(instance!.protocols).toEqual(['bearer', PLACEHOLDER_TOKEN])
  })

  it('defers the connection without a token, and never opens a WebSocket', async () => {
    const store = useUserStore()
    store.authState.token = ''

    const service = new LiveEventService()
    await service.connect()

    expect(MockWebSocket.getLatestInstance()).toBeUndefined()
  })
})
