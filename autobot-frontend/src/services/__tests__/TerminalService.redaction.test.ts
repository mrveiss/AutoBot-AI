// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Guard test for TerminalService's redacted invalid-URL error message (#14989).
 *
 * _validateWsUrl throws `Invalid WebSocket URL: ${wsUrl}` when the resolved
 * URL is not ws://wss://, and the thrown Error's .message reaches
 * logger.error('Failed to connect...', err) through _handleConnectCatchError.
 * connect() itself no longer embeds the JWT in the URL (#16457: it travels
 * as a Sec-WebSocket-Protocol subprotocol instead) -- these tests drive
 * _validateWsUrl/_handleConnectCatchError directly with a synthetic
 * token-bearing URL to pin the redaction as defense in depth regardless of
 * what produced the URL, the same way redactUrlForLogging.ts documents it.
 *
 * baseUrl is always resolved to a valid ws://wss:// prefix in normal use
 * (_resolveWsBaseUrl falls back to a hardcoded valid URL otherwise), so this
 * branch is a defensive guard rather than one reachable through connect()'s
 * public happy path today. Drives the real private method on the real
 * exported singleton (not a reimplementation) rather than asserting against
 * redactUrlForLogging() directly.
 */

import { describe, it, expect, vi } from 'vitest'
import terminalService from '../TerminalService'

describe('TerminalService invalid-URL error redaction (#14989)', () => {
  it('redacts the token in the thrown message when the resolved URL is not ws/wss', () => {
    const svc = terminalService as unknown as { _validateWsUrl: (u: string) => void }
    const TOKEN = 'eyJhbGciOiJSUzI1NiJ9.secret-payload.sig'
    const badUrl = `http://backend.example/api/terminal/ws/session-1?token=${TOKEN}`

    let caught: Error | null = null
    try {
      svc._validateWsUrl(badUrl)
    } catch (e) {
      caught = e as Error
    }

    expect(caught).not.toBeNull()
    expect(caught?.message).toContain('token=REDACTED')
    expect(caught?.message).not.toContain(TOKEN)
  })

  it('redacts the token in the connection-error log via _handleConnectCatchError (#14989 follow-up)', () => {
    // _validateWsUrl closes the wrong-scheme case above, but not every
    // WHATWG URL parse failure -- a native new WebSocket() SyntaxError can
    // still embed the raw token-bearing URL in .message.
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const svc = terminalService as unknown as {
      _handleConnectCatchError: (
        sessionId: string,
        error: unknown,
        reject: (reason: Error) => void,
      ) => void
    }
    const TOKEN = 'eyJhbGciOiJSUzI1NiJ9.secret-payload.sig'
    const syntaxError = new SyntaxError(
      `Failed to construct 'WebSocket': The URL's scheme must be either 'ws' or 'wss'. ` +
        `'http://backend.example/api/terminal/ws/session-1?token=${TOKEN}' is not allowed.`,
    )

    try {
      svc._handleConnectCatchError('redaction-test-session', syntaxError, () => {})

      const loggedArgs = consoleErrorSpy.mock.calls
        .flat()
        .map((a) => (a instanceof Error ? `${a.name}: ${a.message}` : String(a)))
      const joined = loggedArgs.join(' ')

      expect(joined).toContain('token=REDACTED')
      expect(joined).not.toContain(TOKEN)
    } finally {
      consoleErrorSpy.mockRestore()
    }
  })
})
