// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createDateFormatter,
  formatDate,
  formatDateTime,
  formatISOString,
  formatTime,
  formatTimeAgo
} from '../format'

const ISO = '2025-10-30T14:30:15Z'
const UTC = { timeZone: 'UTC' } as const

afterEach(() => vi.useRealTimers())

describe('createDateFormatter (#19905)', () => {
  it('formats the part asked for, in the locale asked for', () => {
    const date = createDateFormatter({ kind: 'date', locale: 'en-US', intl: UTC })
    const time = createDateFormatter({ kind: 'time', locale: 'en-US', intl: { ...UTC, hour12: false } })
    const both = createDateFormatter({ locale: 'en-US', intl: UTC })
    expect(date(ISO)).toBe('10/30/2025')
    expect(time(ISO)).toBe('14:30:15')
    expect(both(ISO)).toBe('10/30/2025, 2:30:15 PM')
  })

  it('reads a number as milliseconds, or as seconds when told', () => {
    const ms = createDateFormatter({ locale: 'en-US', intl: UTC })
    const secs = createDateFormatter({ locale: 'en-US', intl: UTC, unit: 'seconds' })
    expect(ms(Date.parse(ISO))).toBe('10/30/2025, 2:30:15 PM')
    expect(secs(Date.parse(ISO) / 1000)).toBe('10/30/2025, 2:30:15 PM')
  })

  it('accepts a Date, and reads the intl fields per call when given a function', () => {
    let zone: Intl.DateTimeFormatOptions = { timeZone: 'UTC' }
    const fmt = createDateFormatter({ kind: 'time', locale: 'en-US', intl: () => ({ ...zone, hour12: false }) })
    expect(fmt(new Date(ISO))).toBe('14:30:15')
    zone = { timeZone: 'Asia/Tokyo' }
    expect(fmt(new Date(ISO))).toBe('23:30:15')
  })

  it('answers a missing value with the empty text and a bad one with the invalid text', () => {
    const fmt = createDateFormatter({ emptyText: '—', invalidText: '?' })
    expect(fmt(null)).toBe('—')
    expect(fmt(undefined)).toBe('—')
    expect(fmt('')).toBe('—')
    expect(fmt('not a date')).toBe('?')
  })

  it('defaults to a blank empty text, the raw input for a bad value, and reads a function empty text per call', () => {
    expect(createDateFormatter()(null)).toBe('')
    expect(createDateFormatter()('not a date')).toBe('not a date')
    let label = 'never'
    const fmt = createDateFormatter({ emptyText: () => label })
    expect(fmt(null)).toBe('never')
    label = 'jamais'
    expect(fmt(null)).toBe('jamais')
  })

  it('treats an epoch of 0 as a date, not as missing', () => {
    expect(createDateFormatter({ locale: 'en-US', intl: UTC })(0)).toBe('1/1/1970, 12:00:00 AM')
  })
})

describe('formatDate / formatDateTime / formatISOString / formatTime (#19905)', () => {
  it('return an empty string for a missing or invalid value', () => {
    expect(formatDate(undefined)).toBe('')
    expect(formatDate('nope')).toBe('')
    expect(formatDateTime(null)).toBe('')
    expect(formatDateTime('nope')).toBe('')
    expect(formatTime(null)).toBe('')
  })

  it('formatDate passes its Intl options through', () => {
    expect(formatDate(ISO, { ...UTC, year: 'numeric', month: 'short', day: 'numeric' })).toMatch(/Oct/)
  })

  it('formatDateTime merges the options over the default fields', () => {
    const text = formatDateTime(ISO, { timeZone: 'UTC', second: '2-digit' })
    expect(text).toMatch(/30/)
    expect(text).toMatch(/:15/)
  })

  it('formatISOString returns an unparseable string unchanged', () => {
    expect(formatISOString('nope')).toBe('nope')
    expect(formatISOString(null)).toBe('')
    expect(formatISOString(ISO)).toBe(new Date(ISO).toLocaleString())
  })

  it('formatTime shows hours and minutes and honours the 24-hour flag', () => {
    expect(formatTime(ISO, true)).toBe(
      new Date(ISO).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
    )
  })
})

describe('formatTimeAgo (#19905)', () => {
  it('walks the tiers from just now to years', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const ago = (seconds: number) => formatTimeAgo(Date.now() - seconds * 1000)
    expect(ago(30)).toBe('just now')
    expect(ago(120)).toBe('2 minutes ago')
    expect(ago(7200)).toBe('2 hours ago')
    expect(ago(172800)).toBe('2 days ago')
    expect(ago(1209600)).toBe('2 weeks ago')
    expect(ago(5184000)).toBe('2 months ago')
    expect(ago(63072000)).toBe('2 years ago')
  })

  it('reads an invalid value as unknown', () => {
    expect(formatTimeAgo('nope')).toBe('unknown')
  })
})
