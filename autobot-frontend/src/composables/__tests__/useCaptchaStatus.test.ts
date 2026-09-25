// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * `openVnc` resolves its URL from SSOT and refuses when there is none (#17423).
 *
 * The function used to prefer a field on the CAPTCHA payload and fall back to a
 * URL it assembled inline from two VITE_* variables with hardcoded defaults --
 * a browser-LOCAL address, correct only where the browser runs beside the user.
 * It failed silently: `window.open` succeeds on a URL pointing at nothing.
 *
 * Both assertions below would pass against the old code for the wrong reason if
 * they only checked "a window opened", so each pins WHICH url and whether a
 * window opened at all.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { effectScope } from 'vue'

// `vi.hoisted`, not a plain `const`: vitest hoists every `vi.mock` call and the
// module imports above these declarations, and `useCaptchaStatus` calls
// `createLogger` at MODULE scope -- so the mock factory runs during import and a
// plain const is still uninitialised ("Cannot access 'mockLoggerError' before
// initialization"). Hoisting the spies with the mocks is the fix.
const { mockGetServiceUrl, mockLoggerError } = vi.hoisted(() => ({
  mockGetServiceUrl: vi.fn(),
  mockLoggerError: vi.fn(),
}))

vi.mock('@/config/ssot-config', () => ({
  getServiceUrl: (name: string) => mockGetServiceUrl(name),
  getApiBase: () => 'http://backend.test',
}))

vi.mock('@/utils/ApiClient', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@/composables/useEventBus', () => ({
  // `subscribe` is the whole API this composable uses (line 96); a mock shaped
  // like `on`/`off` destructures to undefined and fails with
  // "subscribe is not a function" before any assertion runs.
  useEventBus: () => ({ subscribe: vi.fn(() => vi.fn()) }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    error: mockLoggerError,
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}))

import { useCaptchaStatus } from '../research/useCaptchaStatus'

/** Run the composable inside a scope, as its siblings' specs do -- it registers
 *  an `onUnmounted` hook and would warn outside one. */
function withCaptchaStatus<T>(fn: (api: ReturnType<typeof useCaptchaStatus>) => T): T {
  const scope = effectScope()
  try {
    return scope.run(() => fn(useCaptchaStatus()))!
  } finally {
    scope.stop()
  }
}

describe('openVnc', () => {
  let openSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    mockGetServiceUrl.mockReset()
    mockLoggerError.mockReset()
    openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
  })

  it('opens exactly the URL SSOT returns', () => {
    mockGetServiceUrl.mockReturnValue('https://browser-host.internal:6080/vnc.html')

    withCaptchaStatus((api) => api.openVnc())

    expect(mockGetServiceUrl).toHaveBeenCalledWith('vnc')
    expect(openSpy).toHaveBeenCalledWith(
      'https://browser-host.internal:6080/vnc.html',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('does not assemble a URL of its own', () => {
    // The regression this file exists for: a host SSOT never mentioned means
    // the function built the address itself.
    mockGetServiceUrl.mockReturnValue('https://browser-host.internal:6080/vnc.html')

    withCaptchaStatus((api) => api.openVnc())

    const opened = String(openSpy.mock.calls[0]?.[0] ?? '')
    expect(opened).toBe('https://browser-host.internal:6080/vnc.html')
    expect(opened).not.toContain('localhost')
  })

  it('opens no window and logs an error when no VNC URL is configured', () => {
    mockGetServiceUrl.mockReturnValue(undefined)

    withCaptchaStatus((api) => api.openVnc())

    expect(openSpy).not.toHaveBeenCalled()
    expect(mockLoggerError).toHaveBeenCalledOnce()
  })

  it('opens no window for an empty string either', () => {
    // `getServiceUrl` returns `string | undefined`; an empty string is the
    // shape a misconfigured accessor produces, and `window.open('')` opens a
    // blank tab rather than failing.
    mockGetServiceUrl.mockReturnValue('')

    withCaptchaStatus((api) => api.openVnc())

    expect(openSpy).not.toHaveBeenCalled()
  })
})
