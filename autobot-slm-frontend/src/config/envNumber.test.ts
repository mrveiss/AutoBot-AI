// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * `getEnvPositiveInt` is the one numeric `VITE_*` reader (#19614). The three
 * parsers it replaced disagreed on 0 and negatives: the client timeout and the
 * SSOT ports accepted them, the named timeouts fell back to their default.
 */

import { describe, it, expect, afterEach, vi } from 'vitest'
import { getEnvPositiveInt } from './ssot-config'

const KEY = 'VITE_TEST_NUMERIC'
const FALLBACK = 30_000

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('getEnvPositiveInt (#19614)', () => {
  it('returns the default when the variable is unset', () => {
    expect(getEnvPositiveInt(KEY, FALLBACK)).toBe(FALLBACK)
  })

  it('returns the default when the variable is empty', () => {
    vi.stubEnv(KEY, '')
    expect(getEnvPositiveInt(KEY, FALLBACK)).toBe(FALLBACK)
  })

  it('returns a valid positive integer', () => {
    vi.stubEnv(KEY, '1500')
    expect(getEnvPositiveInt(KEY, FALLBACK)).toBe(1500)
  })

  it('returns the default for zero, not an immediate timeout', () => {
    vi.stubEnv(KEY, '0')
    expect(getEnvPositiveInt(KEY, FALLBACK)).toBe(FALLBACK)
  })

  it('returns the default for a negative value', () => {
    vi.stubEnv(KEY, '-5')
    expect(getEnvPositiveInt(KEY, FALLBACK)).toBe(FALLBACK)
  })

  it('returns the default for a non-numeric value', () => {
    vi.stubEnv(KEY, 'abc')
    expect(getEnvPositiveInt(KEY, FALLBACK)).toBe(FALLBACK)
  })
})
