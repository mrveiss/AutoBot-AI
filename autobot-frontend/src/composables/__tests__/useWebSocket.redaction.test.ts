// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Guard tests for the WebSocket URL credential redaction fix (#14989).
 *
 * useWebSocket.connect() logs the connection URL on open, and on an invalid
 * URL, verbatim. Before #14989 that URL never carried a credential; after it,
 * buildAuthenticatedWsUrl (#6700) puts a JWT in `?token=...`, so those log
 * lines started writing the live token into the console.
 *
 * These tests drive the real useWebSocket composable and the real
 * @/utils/debugUtils logger (console.info/console.error spies, not a mocked
 * logger) -- the bug is that the COMPOSABLE logs the raw value, so a test
 * that only exercises redactUrlForLogging() in isolation would pass even if
 * connect() stopped calling it.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useWebSocket } from '../useWebSocket'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

const TOKEN = 'eyJhbGciOiJSUzI1NiJ9.super-secret-payload.signature'

describe('useWebSocket URL credential redaction (#14989)', () => {
  let consoleInfoSpy: ReturnType<typeof vi.spyOn>
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.mockImplementation()
    MockWebSocket.clearInstances()
    consoleInfoSpy = vi.spyOn(console, 'info').mockImplementation(() => {})
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    consoleInfoSpy.mockRestore()
    consoleErrorSpy.mockRestore()
    vi.useRealTimers()
  })

  it('redacts the token when logging a successful connection', async () => {
    const url = `wss://backend.example/api/terminal/ws/session-1?token=${TOKEN}&conversation_id=abc`

    useWebSocket(url, { autoReconnect: false })
    // MockWebSocket fires onopen after a 10ms setTimeout.
    await vi.advanceTimersByTimeAsync(20)

    const loggedArgs = consoleInfoSpy.mock.calls.flat().map(String)
    const joined = loggedArgs.join(' ')

    expect(joined).toContain('token=REDACTED')
    expect(joined).not.toContain(TOKEN)
    // The rest of the URL -- diagnostically useful -- must survive.
    expect(joined).toContain('conversation_id=abc')
  })

  it('redacts the token when logging an invalid (empty) URL, and does not throw', async () => {
    expect(() => {
      useWebSocket('', { autoReconnect: false })
    }).not.toThrow()

    const loggedArgs = consoleErrorSpy.mock.calls.flat().map(String)
    expect(loggedArgs.some((a) => a.includes('Invalid URL'))).toBe(true)
    expect(loggedArgs.join(' ')).not.toContain(TOKEN)
  })

  it('redacts the token in the connection-error log when new WebSocket() throws (#14989 follow-up)', () => {
    // buildAuthenticatedWsUrl does plain string concatenation with no scheme
    // check -- a misconfigured base URL (http:// where ws:// was meant)
    // reaches new WebSocket(), which throws a SyntaxError embedding the
    // full attempted URL verbatim in every major browser.
    class ThrowingWebSocket {
      constructor(url: string) {
        throw new SyntaxError(
          `Failed to construct 'WebSocket': The URL's scheme must be either 'ws' or 'wss'. '${url}' is not allowed.`,
        )
      }
    }
    const originalWebSocket = globalThis.WebSocket
    globalThis.WebSocket = ThrowingWebSocket as unknown as typeof WebSocket

    try {
      const url = `http://backend.example/api/terminal/ws/session-1?token=${TOKEN}`

      expect(() => {
        useWebSocket(url, { autoReconnect: false })
      }).not.toThrow()

      const loggedArgs = consoleErrorSpy.mock.calls
        .flat()
        .map((a) => (a instanceof Error ? `${a.name}: ${a.message}` : String(a)))
      const joined = loggedArgs.join(' ')

      expect(joined).toContain('token=REDACTED')
      expect(joined).not.toContain(TOKEN)
    } finally {
      globalThis.WebSocket = originalWebSocket
    }
  })
})
