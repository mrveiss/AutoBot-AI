// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * `getEnvPositiveInt` is the one numeric `VITE_*` reader (#19614, #20135). The
 * parsers it replaced disagreed on 0 and negatives.
 */

import { describe, it, expect } from 'vitest'
import { getEnvPositiveInt } from '../env'

const KEY = 'VITE_TEST_NUMERIC'
const FALLBACK = 30_000
const read = (value?: unknown) => getEnvPositiveInt(value === undefined ? {} : { [KEY]: value }, KEY, FALLBACK)

describe('getEnvPositiveInt', () => {
  it('returns the default when the variable is unset', () => expect(read()).toBe(FALLBACK))
  it('returns the default when the variable is empty', () => expect(read('')).toBe(FALLBACK))
  it('returns the default when the variable is null', () => expect(read(null)).toBe(FALLBACK))
  it('returns a valid positive integer', () => expect(read('1500')).toBe(1500))
  it('accepts a number-typed value', () => expect(read(1500)).toBe(1500))
  it('returns the default for zero, not an immediate timeout', () => expect(read('0')).toBe(FALLBACK))
  it('returns the default for a negative value', () => expect(read('-5')).toBe(FALLBACK))
  it('returns the default for a non-numeric value', () => expect(read('abc')).toBe(FALLBACK))
  it('reads the env object it is given, not a global', () => {
    expect(getEnvPositiveInt({ [KEY]: '7' }, KEY, FALLBACK)).toBe(7)
    expect(getEnvPositiveInt({ [KEY]: '9' }, KEY, FALLBACK)).toBe(9)
  })
})
