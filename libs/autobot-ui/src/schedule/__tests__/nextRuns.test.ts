// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Advisory nextRuns tests (#18432): cron, calendar subset, once, DST.

import { describe, it, expect } from 'vitest'
import { compilePickerRule, nextRuns } from '..'
import type { PickerRule, ScheduleSpec } from '..'

const iso = (runs: Date[] | null) => runs?.map((d) => d.toISOString())
const at = (s: string) => new Date(s)
const utc = (rule: PickerRule) => compilePickerRule(rule, 'UTC')
const monthly = (on: Extract<PickerRule, { repeat: 'monthly' }>['on']) =>
  utc({ repeat: 'monthly', time: '09:00', on })

describe('nextRuns: cron', () => {
  it('weekdays 09:00 skips the weekend', () => {
    const spec = utc({ repeat: 'daily', time: '09:00', weekdaysOnly: true })
    expect(iso(nextRuns(spec, 3, at('2026-10-09T10:00:00Z')))).toEqual([
      '2026-10-12T09:00:00.000Z', '2026-10-13T09:00:00.000Z', '2026-10-14T09:00:00.000Z'])
  })

  it('a run exactly at `after` is not "next"', () => {
    const spec = utc({ repeat: 'hourly', minute: 0 })
    expect(iso(nextRuns(spec, 1, at('2026-10-09T10:00:00Z')))).toEqual(['2026-10-09T11:00:00.000Z'])
  })

  it('every 15 minutes within a window', () => {
    const spec = utc({ repeat: 'minutes', every: 15, window: { from: '08:00', to: '09:00' } })
    expect(iso(nextRuns(spec, 5, at('2026-10-09T08:40:00Z')))).toEqual([
      '2026-10-09T08:45:00.000Z', '2026-10-10T08:00:00.000Z', '2026-10-10T08:15:00.000Z',
      '2026-10-10T08:30:00.000Z', '2026-10-10T08:45:00.000Z'])
  })

  it('day-of-month OR day-of-week when both are restricted (Vixie)', () => {
    const spec: ScheduleSpec = { kind: 'cron', timezone: 'UTC', cron: '0 9 13 * 5' }
    expect(iso(nextRuns(spec, 3, at('2026-10-01T00:00:00Z')))).toEqual([
      '2026-10-02T09:00:00.000Z', '2026-10-09T09:00:00.000Z', '2026-10-13T09:00:00.000Z'])
  })

  it('reads a plain 29 Feb cron across years', () => {
    const spec: ScheduleSpec = { kind: 'cron', timezone: 'UTC', cron: '0 0 29 2 *' }
    expect(iso(nextRuns(spec, 1, at('2026-03-01T00:00:00Z')))).toEqual(['2028-02-29T00:00:00.000Z'])
  })

  it.each(['0 0 9 * * 1-5', '0 9 * * 5L', '0 9 L * *', '@daily', 'x'])('cannot compute %s → null', (c) => {
    expect(nextRuns({ kind: 'cron', timezone: 'UTC', cron: c }, 3, at('2026-10-09T10:00:00Z'))).toBeNull()
  })

  it('unknown zone → null', () => {
    expect(nextRuns({ kind: 'cron', timezone: 'Mars/Base', cron: '0 9 * * *' }, 3)).toBeNull()
  })
})

describe('nextRuns: monthly shapes', () => {
  it('day 31 runs on the last day of shorter months (Feb, 30-day months)', () => {
    expect(iso(nextRuns(monthly({ day: 31 }), 5, at('2026-01-31T12:00:00Z')))).toEqual([
      '2026-02-28T09:00:00.000Z', '2026-03-31T09:00:00.000Z', '2026-04-30T09:00:00.000Z',
      '2026-05-31T09:00:00.000Z', '2026-06-30T09:00:00.000Z'])
  })

  it('day 30 runs on 28/29 in February, leap year included', () => {
    expect(iso(nextRuns(monthly({ day: 30 }), 1, at('2026-02-01T00:00:00Z')))).toEqual(['2026-02-28T09:00:00.000Z'])
    expect(iso(nextRuns(monthly({ day: 30 }), 1, at('2028-02-01T00:00:00Z')))).toEqual(['2028-02-29T09:00:00.000Z'])
  })

  it('day 29 on a non-leap February is the 28th', () => {
    expect(iso(nextRuns(monthly({ day: 29 }), 2, at('2026-02-01T00:00:00Z')))).toEqual([
      '2026-02-28T09:00:00.000Z', '2026-03-29T09:00:00.000Z'])
  })

  it('last day of month', () => {
    expect(iso(nextRuns(monthly({ lastDay: true }), 3, at('2027-12-31T10:00:00Z')))).toEqual([
      '2028-01-31T09:00:00.000Z', '2028-02-29T09:00:00.000Z', '2028-03-31T09:00:00.000Z'])
  })

  it('last Friday and second Tuesday', () => {
    expect(iso(nextRuns(monthly({ nth: -1, weekday: 'FR' }), 2, at('2026-10-01T00:00:00Z')))).toEqual([
      '2026-10-30T09:00:00.000Z', '2026-11-27T09:00:00.000Z'])
    expect(iso(nextRuns(monthly({ nth: 2, weekday: 'TU' }), 2, at('2026-10-01T00:00:00Z')))).toEqual([
      '2026-10-13T09:00:00.000Z', '2026-11-10T09:00:00.000Z'])
  })

  it('first weekday that does not occur is skipped, not invented', () => {
    // 5th occurrence is unsupported by the picker; direct rrule still must not invent dates
    const spec: ScheduleSpec = { kind: 'calendar', timezone: 'UTC', rrule: 'FREQ=MONTHLY;BYDAY=5MO;BYHOUR=9;BYMINUTE=0' }
    expect(iso(nextRuns(spec, 2, at('2026-10-01T00:00:00Z')))).toEqual([
      '2026-11-30T09:00:00.000Z', '2027-03-29T09:00:00.000Z'])
  })

  it.each(['FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0', 'FREQ=MONTHLY;BYMONTHDAY=1;COUNT=2;BYHOUR=9;BYMINUTE=0',
    'DTSTART=20260101T000000;FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=9;BYMINUTE=0', 'FREQ=MONTHLY;BYMONTHDAY=1'])(
    'unsupported rrule %s → null', (r) => {
      expect(nextRuns({ kind: 'calendar', timezone: 'UTC', rrule: r }, 2, at('2026-10-01T00:00:00Z'))).toBeNull()
    })
})

describe('nextRuns: once', () => {
  it('future → one run in the spec zone; past → none', () => {
    const spec: ScheduleSpec = { kind: 'once', timezone: 'Europe/Helsinki', at: '2026-12-24T08:00' }
    expect(iso(nextRuns(spec, 3, at('2026-10-01T00:00:00Z')))).toEqual(['2026-12-24T06:00:00.000Z'])
    expect(nextRuns(spec, 3, at('2027-01-01T00:00:00Z'))).toEqual([])
  })
  it('malformed at → null', () => {
    expect(nextRuns({ kind: 'once', timezone: 'UTC', at: 'soon' }, 1)).toBeNull()
  })
})

describe('nextRuns: DST (Europe/Helsinki 2026: forward 29 Mar 03:00, back 25 Oct 04:00)', () => {
  const hel = (rule: PickerRule) => compilePickerRule(rule, 'Europe/Helsinki')

  it('09:00 local keeps its wall time across spring-forward (UTC hour moves)', () => {
    const spec = hel({ repeat: 'daily', time: '09:00', weekdaysOnly: false })
    expect(iso(nextRuns(spec, 3, at('2026-03-27T12:00:00Z')))).toEqual([
      '2026-03-28T07:00:00.000Z', '2026-03-29T06:00:00.000Z', '2026-03-30T06:00:00.000Z'])
  })

  it('09:00 local keeps its wall time across fall-back', () => {
    const spec = hel({ repeat: 'daily', time: '09:00', weekdaysOnly: false })
    expect(iso(nextRuns(spec, 3, at('2026-10-24T12:00:00Z')))).toEqual([
      '2026-10-25T07:00:00.000Z', '2026-10-26T07:00:00.000Z', '2026-10-27T07:00:00.000Z'])
  })

  it('a nonexistent local time (03:30 on spring-forward) runs shifted forward, once', () => {
    const spec = hel({ repeat: 'daily', time: '03:30', weekdaysOnly: false })
    expect(iso(nextRuns(spec, 3, at('2026-03-28T12:00:00Z')))).toEqual([
      '2026-03-29T01:30:00.000Z', '2026-03-30T00:30:00.000Z', '2026-03-31T00:30:00.000Z'])
  })

  it('an ambiguous local time (03:30 on fall-back) runs once, at the first occurrence', () => {
    const spec = hel({ repeat: 'daily', time: '03:30', weekdaysOnly: false })
    expect(iso(nextRuns(spec, 3, at('2026-10-24T12:00:00Z')))).toEqual([
      '2026-10-25T00:30:00.000Z', '2026-10-26T01:30:00.000Z', '2026-10-27T01:30:00.000Z'])
  })

  it('last Friday across the autumn shift uses each date\'s own offset', () => {
    const spec = hel({ repeat: 'monthly', time: '09:00', on: { nth: -1, weekday: 'FR' } })
    expect(iso(nextRuns(spec, 2, at('2026-10-01T00:00:00Z')))).toEqual([
      '2026-10-30T07:00:00.000Z', '2026-11-27T07:00:00.000Z'])
  })

  it('a zone west of UTC rolls the local date, not the UTC date', () => {
    const spec = compilePickerRule({ repeat: 'daily', time: '22:00', weekdaysOnly: false }, 'America/Los_Angeles')
    expect(iso(nextRuns(spec, 1, at('2026-10-09T03:00:00Z')))).toEqual(['2026-10-09T05:00:00.000Z'])
  })
})
