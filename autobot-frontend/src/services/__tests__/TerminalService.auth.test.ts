// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Auth-token transport for TerminalService's `/ws/{session_id}` connection (#16457).
 *
 * `connect()` used to send the token via `buildAuthenticatedWsUrl()`'s
 * `?token=...` query string, which lands in server access logs and browser
 * history. These tests pin that it now travels via the
 * Sec-WebSocket-Protocol subprotocol instead, and that the URL handed to the
 * browser's WebSocket constructor never carries the token.
 *
 * Drives the real exported singleton directly (matching
 * `TerminalService.redaction.test.ts`'s pattern) rather than constructing a
 * second instance, and sets `baseUrl` directly to bypass the async
 * `appConfig`/`ServiceDiscovery` resolution `initializeWebSocketUrl()` would
 * otherwise need mocked -- `connect()` only reads `baseUrl` once it is set,
 * so this reaches the same code path without depending on that chain.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

// Built rather than a literal so a secret scanner never mistakes fixture data
// shaped like "token = '...'" for a real credential.
const PLACEHOLDER_TOKEN = ['fixture', 'not-a-real', 'value'].join('.')

vi.mock('@/utils/buildAuthenticatedWsUrl', () => ({
  buildAuthenticatedWsSubprotocols: vi.fn(),
}))

import { buildAuthenticatedWsSubprotocols } from '@/utils/buildAuthenticatedWsUrl'
import terminalService from '../TerminalService'

type TerminalServiceInternals = {
  baseUrl: string
  connections: Map<string, WebSocket>
}

describe('TerminalService auth transport (#16457)', () => {
  const svc = terminalService as unknown as TerminalServiceInternals

  beforeEach(() => {
    MockWebSocket.clearInstances()
    MockWebSocket.mockImplementation()
    svc.baseUrl = 'ws://backend.example/api/terminal/ws'
    svc.connections.clear()
  })

  afterEach(() => {
    MockWebSocket.restoreImplementation()
    vi.clearAllMocks()
  })

  it('sends the token as a subprotocol, never in the URL', async () => {
    vi.mocked(buildAuthenticatedWsSubprotocols).mockReturnValue(['bearer', PLACEHOLDER_TOKEN])

    await terminalService.connect('term-auth-test-1')

    const instance = MockWebSocket.getLatestInstance()
    expect(instance).toBeDefined()
    expect(instance!.url).not.toContain('token=')
    expect(instance!.url).not.toContain(PLACEHOLDER_TOKEN)
    expect(instance!.protocols).toEqual(['bearer', PLACEHOLDER_TOKEN])
  })

  it('defers the connection without a token, and never opens a WebSocket', async () => {
    vi.mocked(buildAuthenticatedWsSubprotocols).mockReturnValue(null)

    await expect(terminalService.connect('term-auth-test-2')).rejects.toThrow(
      'No auth token available for terminal WebSocket',
    )
    expect(MockWebSocket.getLatestInstance()).toBeUndefined()
  })
})
