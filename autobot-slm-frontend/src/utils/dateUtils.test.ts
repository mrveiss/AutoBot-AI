// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** formatCompactRelativeTime (#19606): narrow Intl relative text in the app locale, capped at days. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const i18nState = vi.hoisted(() => ({ locale: 'en' }))
vi.mock('@/i18n', () => ({ default: { global: i18nState } }))

import { formatCompactRelativeTime } from './dateUtils'

const NOW = Date.parse('2026-11-02T12:00:00Z')
const ago = (seconds: number): string => new Date(NOW - seconds * 1000).toISOString()

describe('formatCompactRelativeTime', () => {
  beforeEach(() => {
    i18nState.locale = 'en'
    vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
  })
  afterEach(() => vi.useRealTimers())

  it.each([
    [5, '5s ago'],
    [180, '3m ago'],
    [7200, '2h ago'],
    [4 * 86400, '4d ago'],
    [45 * 86400, '45d ago']
  ])('%i seconds back reads %s', (seconds, expected) => {
    expect(formatCompactRelativeTime(ago(seconds))).toBe(expected)
  })

  it('accepts a Date and epoch milliseconds', () => {
    expect(formatCompactRelativeTime(new Date(NOW - 120_000))).toBe('2m ago')
    expect(formatCompactRelativeTime(NOW - 120_000)).toBe('2m ago')
  })

  it('answers a missing or unparseable value with a dash', () => {
    expect(formatCompactRelativeTime(null)).toBe('—')
    expect(formatCompactRelativeTime('not a date')).toBe('—')
  })

  it('follows the app locale on every call', () => {
    i18nState.locale = 'de'
    expect(formatCompactRelativeTime(ago(7200))).toContain('vor 2')
  })
})
