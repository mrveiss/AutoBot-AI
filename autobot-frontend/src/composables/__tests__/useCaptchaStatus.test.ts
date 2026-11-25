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
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

// `vi.hoisted`, not a plain `const`: vitest hoists every `vi.mock` call and the
// module imports above these declarations, and `useCaptchaStatus` calls
// `createLogger` at MODULE scope -- so the mock factory runs during import and a
// plain const is still uninitialised ("Cannot access 'mockLoggerError' before
// initialization"). Hoisting the spies with the mocks is the fix.
const { mockGetServiceUrl, mockLoggerError, mockSubscribe } = vi.hoisted(() => ({
  mockGetServiceUrl: vi.fn(),
  mockLoggerError: vi.fn(),
  mockSubscribe: vi.fn(() => vi.fn()),
}))

vi.mock('@/config/ssot-config', () => ({
  getServiceUrl: (name: string) => mockGetServiceUrl(name),
  getApiBase: () => 'http://backend.test',
}))

vi.mock('@/utils/ApiClient', () => ({
  default: { get: vi.fn(), post: vi.fn(), call: vi.fn() },
}))

vi.mock('@/composables/useEventBus', () => ({
  // `subscribe` is the whole API this composable uses (line 96); a mock shaped
  // like `on`/`off` destructures to undefined and fails with
  // "subscribe is not a function" before any assertion runs.
  useEventBus: () => ({ subscribe: mockSubscribe }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    error: mockLoggerError,
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}))

import { captchaTypeLabelKeyFor, useCaptchaStatus } from '../research/useCaptchaStatus'
import apiClient from '@/utils/ApiClient'

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

describe('captchaTypeLabelKeyFor', () => {
  const en = JSON.parse(readFileSync(resolve(__dirname, '../../i18n/locales/en.json'), 'utf-8'))
  const localeFiles = readdirSync(resolve(__dirname, '../../i18n/locales')).filter((f) => f.endsWith('.json'))

  it.each([
    ['recaptcha', 'recaptcha'],
    ['hcaptcha', 'hcaptcha'],
    ['cloudflare', 'cloudflare'],
    ['slider', 'slider'],
    ['image_select', 'imageSelect'],
    ['text', 'text'],
    ['text_image', 'text'],
    ['math', 'math'],
    ['unknown', 'unknown'],
  ])('maps %s to its own label', (wire, slug) => {
    expect(captchaTypeLabelKeyFor(wire)).toBe(`research.captcha.types.${slug}`)
  })

  it.each([undefined, '', 'nonsense'])('shows the unknown label for %s', (wire) => {
    expect(captchaTypeLabelKeyFor(wire)).toBe('research.captcha.types.unknown')
  })

  it('every key it can return exists in all 11 locales', () => {
    expect(localeFiles).toHaveLength(11)
    const keys = new Set(
      ['recaptcha', 'hcaptcha', 'cloudflare', 'slider', 'image_select', 'text', 'math', 'unknown', 'x'].map(
        captchaTypeLabelKeyFor,
      ),
    )
    for (const file of localeFiles) {
      const types = JSON.parse(readFileSync(resolve(__dirname, '../../i18n/locales', file), 'utf-8')).research.captcha.types
      for (const key of keys) expect(types[key.split('.').pop()!], `${file}: ${key}`).toBeTruthy()
    }
    expect(Object.keys(en.research.captcha.types)).toHaveLength(8)
  })
})

describe('loadPendingCaptchas (#22215)', () => {
  const get = apiClient.call as unknown as ReturnType<typeof vi.fn>

  beforeEach(() => {
    get.mockReset()
    mockLoggerError.mockReset()
  })

  it('calls GET /captcha/pending and shows the first still-pending CAPTCHA', async () => {
    get.mockResolvedValue({
      success: true,
      count: 2,
      timestamp: 't0',
      pending_captchas: { done: { status: 'solved' }, waiting: { status: 'pending' } },
    })

    const shown = await withCaptchaStatus(async (api) => {
      await api.loadPendingCaptchas()
      return api.activeCaptcha.value
    })

    expect(get).toHaveBeenCalledExactlyOnceWith('get', '/api/captcha/pending')
    expect(shown?.captcha_id).toBe('waiting')
    expect(shown?.timeout_seconds).toBeGreaterThan(0)
  })

  it('reads the DataResponse-wrapped body the contract declares as well', async () => {
    get.mockResolvedValue({ success: true, data: { success: true, count: 1, timestamp: 't0', pending_captchas: { w: { status: 'pending' } } } })

    const shown = await withCaptchaStatus(async (api) => {
      await api.loadPendingCaptchas()
      return api.activeCaptcha.value
    })

    expect(shown?.captcha_id).toBe('w')
  })

  it('shows nothing when none is pending', async () => {
    get.mockResolvedValue({ success: true, count: 0, timestamp: 't0', pending_captchas: {} })

    const shown = await withCaptchaStatus(async (api) => {
      await api.loadPendingCaptchas()
      return api.activeCaptcha.value
    })

    expect(shown).toBeNull()
  })

  it('logs and shows nothing when the route fails', async () => {
    get.mockRejectedValue(new Error('500'))

    const shown = await withCaptchaStatus(async (api) => {
      await api.loadPendingCaptchas()
      return api.activeCaptcha.value
    })

    expect(shown).toBeNull()
    expect(mockLoggerError).toHaveBeenCalledOnce()
  })

  it('flags a failed restore apart from an empty one, and clears the flag on retry', async () => {
    get.mockRejectedValueOnce(new Error('500'))
    get.mockResolvedValueOnce({ success: true, count: 0, timestamp: 't0', pending_captchas: {} })

    const flags = await withCaptchaStatus(async (api) => {
      await api.loadPendingCaptchas()
      const afterFailure = api.pendingLoadFailed.value
      await api.loadPendingCaptchas()
      return { afterFailure, afterEmpty: api.pendingLoadFailed.value }
    })

    expect(flags).toEqual({ afterFailure: true, afterEmpty: false })
  })

  it('does not restore a CAPTCHA whose terminal event arrived first', async () => {
    let reply!: (v: unknown) => void
    get.mockImplementation(() => new Promise((r) => (reply = r)))

    const shown = await withCaptchaStatus(async (api) => {
      const loading = api.loadPendingCaptchas()
      const handler = (mockSubscribe.mock.calls.at(-1) as unknown as [string, (e: unknown) => void])[1]
      handler({ event_type: 'captcha_resolved', payload: { captcha_id: 'gone' } })
      reply({ success: true, count: 1, timestamp: 't0', pending_captchas: { gone: { status: 'pending' } } })
      await loading
      return api.activeCaptcha.value
    })

    expect(shown).toBeNull()
  })
})
