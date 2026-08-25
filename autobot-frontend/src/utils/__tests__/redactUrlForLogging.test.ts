// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Unit tests for redactUrlForLogging's own contract (#14989 follow-up).
 *
 * Unlike useWebSocket.redaction.test.ts and TerminalService.redaction.test.ts
 * -- which drive a real caller to prove the composable/service actually
 * calls this helper -- these two cases are about the helper's own edge-case
 * behaviour: no current call site puts a credential in a URL fragment or
 * calls this with a non-string, so there is no "real path" to drive for
 * them. Both were confirmed reachable-in-principle by execution during
 * review (a `new URL(...).toString()` never touches `.hash`, and the
 * doc-commented "never throws" was not literally true for a non-string
 * argument bypassing the TS type system), so they are tested directly.
 */

import { describe, it, expect } from 'vitest'
import { redactUrlForLogging, redactErrorForLogging } from '@/utils/redactUrlForLogging'

describe('redactUrlForLogging', () => {
  it('redacts a token carried in the URL fragment, not only the query string', () => {
    // URLSearchParams never looks at `.hash` -- new URL(...).toString()
    // alone would leave this untouched.
    const url = 'wss://backend.example/api/ws?x=1#token=FRAGMENT_SECRET'
    const redacted = redactUrlForLogging(url)

    expect(redacted).toContain('token=REDACTED')
    expect(redacted).not.toContain('FRAGMENT_SECRET')
    expect(redacted).toContain('x=1')
  })

  it('never throws for a non-string argument, despite the TS signature', () => {
    // The compiled app cannot reach this (every call site is typed
    // `string`) -- this proves the doc comment's "never throws, for real"
    // claim rather than assuming the type system enforces it at runtime.
    expect(() => redactUrlForLogging(null as unknown as string)).not.toThrow()
    expect(() => redactUrlForLogging(undefined as unknown as string)).not.toThrow()
    expect(redactUrlForLogging(null as unknown as string)).toBe('null')
    expect(redactUrlForLogging(undefined as unknown as string)).toBe('undefined')
  })
})

describe('redactErrorForLogging', () => {
  it('redacts a token embedded in an Error message while preserving type and stack', () => {
    const original = new Error(
      "Failed to construct 'WebSocket': The URL's scheme must be either 'ws' or 'wss'. " +
        "'http://backend.example/ws?token=LEAKED_SECRET' is not allowed.",
    )
    original.name = 'SyntaxError'

    const redacted = redactErrorForLogging(original) as Error

    expect(redacted).toBeInstanceOf(Error)
    expect(redacted.name).toBe('SyntaxError')
    expect(redacted.message).toContain('token=REDACTED')
    expect(redacted.message).not.toContain('LEAKED_SECRET')
    expect(redacted.stack).toBe(original.stack)
  })

  it('passes non-Error values through unchanged', () => {
    expect(redactErrorForLogging('a plain string')).toBe('a plain string')
    expect(redactErrorForLogging(42)).toBe(42)
    expect(redactErrorForLogging(null)).toBeNull()
  })
})
