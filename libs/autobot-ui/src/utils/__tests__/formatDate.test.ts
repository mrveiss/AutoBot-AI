// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createDateFormatter,
  formatDate,
  formatDateTime,
  formatISOString,
  formatTime,
  formatRelativeTime,
  formatLocalTime,
  createRecencyFormatter
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
  it('formatDateTime takes a style option without the default fields Intl rejects beside it', () => {
    const iso = '2026-01-15T10:30:00Z'
    expect(() => formatDateTime(iso, { dateStyle: 'short' })).not.toThrow()
    expect(formatDateTime(iso, { dateStyle: 'short' })).toBe(new Date(iso).toLocaleString(undefined, { dateStyle: 'short' }))
    expect(() => formatDateTime(iso, { timeStyle: 'short' })).not.toThrow()
  })

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

  it('formatISOString answers an unparseable string with the empty string, like formatDate', () => {
    expect(formatISOString('nope')).toBe('')
    expect(formatISOString(null)).toBe('')
    expect(formatISOString(ISO)).toBe(new Date(ISO).toLocaleString())
  })

  it('formatTime shows hours and minutes and honours the 24-hour flag', () => {
    expect(formatTime(ISO, true)).toBe(
      new Date(ISO).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
    )
  })
})

describe('formatRelativeTime (#19606)', () => {
  const NOW = Date.parse('2026-01-01T00:00:00Z')
  const ago = (seconds: number, options = {}) =>
    formatRelativeTime(NOW - seconds * 1000, { locale: 'en', now: NOW, ...options })

  it('walks the units on Intl.RelativeTimeFormat', () => {
    expect(ago(0)).toBe('0 seconds ago')
    expect(ago(5)).toBe('5 seconds ago')
    expect(ago(1)).toBe('1 second ago')
    expect(ago(180)).toBe('3 minutes ago')
    expect(ago(7200)).toBe('2 hours ago')
    expect(ago(345600)).toBe('4 days ago')
    expect(ago(1209600)).toBe('2 weeks ago')
    expect(ago(5184000)).toBe('2 months ago')
    expect(ago(63072000)).toBe('2 years ago')
  })

  it('reads a future moment as in the future', () => {
    expect(ago(-7200)).toBe('in 2 hours')
  })

  it('narrow style is the compact 5s / 3m / 2h / 4d form', () => {
    expect(ago(5, { style: 'narrow' })).toBe('5s ago')
    expect(ago(180, { style: 'narrow' })).toBe('3m ago')
    expect(ago(7200, { style: 'narrow' })).toBe('2h ago')
    expect(ago(345600, { style: 'narrow' })).toBe('4d ago')
  })

  it('maxUnit counts a longer span in that unit', () => {
    expect(ago(3888000, { maxUnit: 'day' })).toBe('45 days ago')
  })

  it('localises through the locale argument', () => {
    expect(ago(7200, { locale: 'de' })).toBe('vor 2 Stunden')
    expect(ago(7200, { locale: 'fr' })).toBe('il y a 2 heures')
  })

  it('keeps the dash, or the caller text, for a missing or unparseable moment', () => {
    expect(formatRelativeTime(null)).toBe('—')
    expect(formatRelativeTime('nope')).toBe('—')
    expect(formatRelativeTime(undefined, { nullText: 'Never' })).toBe('Never')
  })

  it('defaults to the current time', () => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
    expect(formatRelativeTime(NOW - 120000, { locale: 'en' })).toBe('2 minutes ago')
    vi.useRealTimers()
  })
})

describe('one answer for a missing or unparseable value (#19905)', () => {
  it("formatDate, formatISOString and formatLocalTime show what the browser's toLocale…String() shows", () => {
    const at = new Date(ISO)
    expect(formatDate(at)).toBe(at.toLocaleDateString())
    expect(formatISOString(at)).toBe(at.toLocaleString())
    expect(formatISOString(ISO)).toBe(at.toLocaleString())
    expect(formatLocalTime(at)).toBe(at.toLocaleTimeString())
  })

  it('every fixed formatter answers a missing AND an unparseable value with the empty string', () => {
    for (const f of [formatDate, formatDateTime, formatISOString, formatLocalTime]) {
      expect(f(undefined)).toBe('')
      expect(f(null)).toBe('')
      expect(f('not a date')).toBe('')
    }
  })
})

describe('createRecencyFormatter (#19606)', () => {
  const NOW = Date.parse('2025-10-30T12:00:00Z')
  const at = (msAgo: number) => new Date(NOW - msAgo)
  const now = () => NOW

  it('says just now under a minute, then relative text in the locale and style given', () => {
    const f = createRecencyFormatter({ justNow: 'just now', locale: 'en', style: 'narrow', now })
    expect(f(at(30_000))).toBe('just now')
    expect(f(at(5 * 60_000))).toBe('5m ago')
    expect(f(at(3 * 3_600_000))).toBe('3h ago')
  })

  it('reads the locale and the just-now text on every call, so a language switch applies', () => {
    let lang = 'en'
    let label = 'just now'
    const f = createRecencyFormatter({ justNow: () => label, locale: () => lang, now })
    expect(f(at(2 * 60_000))).toBe('2 minutes ago')
    lang = 'de'
    label = 'gerade eben'
    expect(f(at(2 * 60_000))).toBe('vor 2 Minuten')
    expect(f(at(1_000))).toBe('gerade eben')
  })

  it('shows the older text at or past the cutoff, a plain date by default', () => {
    const day = 86_400_000
    const f = createRecencyFormatter({ olderThanMs: day, locale: 'en', now })
    expect(f(at(day - 1))).toBe('23 hours ago')
    expect(f(at(day))).toBe(at(day).toLocaleDateString())
    const g = createRecencyFormatter({ olderThanMs: day, older: () => 'long ago', now })
    expect(g(at(2 * day))).toBe('long ago')
  })

  it('shows a time of day past the cutoff when the older text is a time formatter', () => {
    const hour = 3_600_000
    const older = createDateFormatter({ kind: 'time', locale: 'en-US', intl: { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', hour12: false } })
    const f = createRecencyFormatter({ olderThanMs: hour, older, locale: 'en', style: 'narrow', now })
    expect(f(at(hour - 1))).toBe('59m ago')
    expect(f(at(hour))).toBe('11:00')
    expect(f(at(2 * hour))).toBe('10:00')
  })

  it('caps the unit and answers a missing or unparseable moment with the invalid text', () => {
    const f = createRecencyFormatter({ locale: 'en', maxUnit: 'day', now, invalidText: '—' })
    expect(f(at(45 * 86_400_000))).toBe('45 days ago')
    expect(f(null)).toBe('—')
    expect(f('not a date')).toBe('—')
    expect(createRecencyFormatter()('nope')).toBe('')
  })

  it('without soon, reads every future moment as just now, as it always has (#19905)', () => {
    const f = createRecencyFormatter({ justNow: 'just now', locale: 'en', now })
    expect(f(new Date(NOW + 30_000))).toBe('just now')
    expect(f(new Date(NOW + 5 * 60_000))).toBe('just now')
    expect(f(new Date(NOW + 3 * 86_400_000))).toBe('just now')
    expect(createRecencyFormatter({ locale: 'en', now })(new Date(NOW + 5 * 60_000))).toBe('in 5 minutes')
  })

  it('with soon, reads a moment under a minute ahead as soon and a later one as "in …"', () => {
    const g = createRecencyFormatter({ justNow: 'just now', soon: 'in a moment', locale: 'en', style: 'narrow', now })
    expect(g(new Date(NOW + 30_000))).toBe('in a moment')
    expect(g(at(30_000))).toBe('just now')
    expect(g(new Date(NOW + 3 * 3_600_000))).toBe('in 3h')
  })

  it.each([
    ['1h', 3_600_000, '59m ago'],
    ['24h', 86_400_000, '23h ago'],
    ['30d', 30 * 86_400_000, '29d ago'],
  ])('switches to the older text exactly at a %s cutoff', (_label, cutoff, justUnder) => {
    const f = createRecencyFormatter({ locale: 'en', style: 'narrow', maxUnit: 'day', olderThanMs: cutoff, older: () => 'older', now })
    expect(f(at(cutoff - 60_000))).toBe(justUnder)
    expect(f(at(cutoff))).toBe('older')
  })
})
