// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// RumAgent.stop() (#18254): the singleton's periodic timers end, so nothing ticks
// after the code that loaded it is gone -- in tests, after jsdom's teardown, where a
// late generateReport() read a localStorage that no longer existed.

import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

/**
 * The first case pays the cold transform of RumAgent's import graph (~3 s alone), which a
 * loaded pre-push stretched past vitest's default 10 s. It gets its own budget, as
 * ThemePresetPicker.test.ts does (#18252), rather than a warm-up import that would load
 * the module before the case sets up what its import reads.
 */
const COLD_IMPORT_MS = 60_000

describe('RumAgent.stop', () => {
  it('clears every periodic timer it started, and no report runs afterwards', async () => {
    vi.useFakeTimers()
    vi.resetModules()
    const rum = (await import('@/utils/RumAgent')).default
    const started = (rum as unknown as { intervals: unknown[] }).intervals.length
    expect(started).toBeGreaterThan(0)
    const report = vi.spyOn(rum, 'generateReport')

    rum.stop()
    vi.advanceTimersByTime(120_000)

    expect((rum as unknown as { intervals: unknown[] }).intervals).toEqual([])
    expect(report).not.toHaveBeenCalled()
  }, COLD_IMPORT_MS)

  it('is safe to call twice', async () => {
    const rum = (await import('@/utils/RumAgent')).default
    rum.stop()
    expect(() => rum.stop()).not.toThrow()
  })
})
