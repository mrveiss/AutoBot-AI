// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #19458 — one window error is reported to RUM exactly once. Uses the REAL
 * RumAgent (it owns the window listener) alongside the real error plugin.
 */
import { describe, it, expect, vi } from 'vitest'

vi.mock('@/stores/useAppStore', () => ({ useAppStore: () => ({ addSystemNotification: vi.fn() }) }))
vi.mock('@/i18n', () => ({ default: { global: { t: (key: string) => key } } }))

/**
 * The first case pays the cold transform of RumAgent's import graph (~3 s alone), which a
 * loaded pre-push stretched past vitest's default 10 s. It gets its own budget, as
 * ThemePresetPicker.test.ts does (#18252), rather than a warm-up import that would load
 * the module before the case sets up what its import reads.
 */
const COLD_IMPORT_MS = 60_000

describe('RUM reporting of window events (#19458)', () => {
  it('reports one window error as exactly one javascript_error', async () => {
    localStorage.setItem('rum_enabled', 'true')
    const { default: rumAgent } = await import('@/utils/RumAgent')
    const spy = vi.spyOn(rumAgent, 'trackError').mockImplementation(() => {})
    await import('../errorHandler')

    window.dispatchEvent(new ErrorEvent('error', { message: 'boom', error: new Error('boom') }))

    const reports = spy.mock.calls.filter(([type]) => type === 'javascript_error')
    expect(reports).toHaveLength(1)
  }, COLD_IMPORT_MS)

  it('reports one unhandled rejection as exactly one unhandled_promise_rejection', async () => {
    const { default: rumAgent } = await import('@/utils/RumAgent')
    const spy = vi.spyOn(rumAgent, 'trackError').mockImplementation(() => {})
    spy.mockClear()
    const event = new Event('unhandledrejection', { cancelable: true }) as Event & { reason: unknown }
    event.reason = new Error('nope')
    window.dispatchEvent(event)
    expect(spy.mock.calls.filter(([type]) => type === 'unhandled_promise_rejection')).toHaveLength(1)
  })
})
