// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Schedule contract tests (#18432): compile, parse, round-trip, summary keys.

import { describe, it, expect } from 'vitest'
import { compilePickerRule, parseSpecToRule, summaryKeys, summaryText, WEEKDAYS } from '..'
import { nextRuns } from '../nextRuns'
import { splitTime } from '../time'
import type { PickerRule, ScheduleSpec } from '..'

const TZ = 'Europe/Helsinki'
const cron = (c: string): ScheduleSpec => ({ kind: 'cron', timezone: 'UTC', cron: c })
const cal = (r: string): ScheduleSpec => ({ kind: 'calendar', timezone: 'UTC', rrule: r })

describe('compilePickerRule', () => {
  const cases: Array<[string, PickerRule, ScheduleSpec]> = [
    ['minutes', { repeat: 'minutes', every: 15 }, { kind: 'cron', timezone: TZ, cron: '*/15 * * * *' }],
    ['minutes window+days', { repeat: 'minutes', every: 30, window: { from: '08:00', to: '18:00' }, days: ['MO', 'TU', 'WE', 'TH', 'FR'] },
      { kind: 'cron', timezone: TZ, cron: '*/30 8-17 * * 1-5' }],
    ['minutes window to 24:00', { repeat: 'minutes', every: 5, window: { from: '20:00', to: '24:00' } },
      { kind: 'cron', timezone: TZ, cron: '*/5 20-23 * * *' }],
    ['minutes full-day window is plain', { repeat: 'minutes', every: 5, window: { from: '00:00', to: '24:00' } },
      { kind: 'cron', timezone: TZ, cron: '*/5 * * * *' }],
    ['hourly', { repeat: 'hourly', minute: 7 }, { kind: 'cron', timezone: TZ, cron: '7 * * * *' }],
    ['daily', { repeat: 'daily', time: '09:00', weekdaysOnly: false }, { kind: 'cron', timezone: TZ, cron: '0 9 * * *' }],
    ['weekdays', { repeat: 'daily', time: '09:30', weekdaysOnly: true }, { kind: 'cron', timezone: TZ, cron: '30 9 * * 1-5' }],
    ['weekly Sat+Sun', { repeat: 'weekly', time: '10:00', days: ['SU', 'SA'] }, { kind: 'cron', timezone: TZ, cron: '0 10 * * 0,6' }],
    ['weekly Mon Wed Fri', { repeat: 'weekly', time: '10:00', days: ['FR', 'MO', 'WE'] }, { kind: 'cron', timezone: TZ, cron: '0 10 * * 1,3,5' }],
    ['weekly Mon-Wed range', { repeat: 'weekly', time: '10:00', days: ['MO', 'TU', 'WE'] }, { kind: 'cron', timezone: TZ, cron: '0 10 * * 1-3' }],
    ['monthly 1', { repeat: 'monthly', time: '06:00', on: { day: 1 } }, { kind: 'cron', timezone: TZ, cron: '0 6 1 * *' }],
    ['monthly 28', { repeat: 'monthly', time: '06:00', on: { day: 28 } }, { kind: 'cron', timezone: TZ, cron: '0 6 28 * *' }],
    ['monthly 29', { repeat: 'monthly', time: '06:00', on: { day: 29 } },
      { kind: 'calendar', timezone: TZ, rrule: 'FREQ=MONTHLY;BYMONTHDAY=28,29;BYSETPOS=-1;BYHOUR=6;BYMINUTE=0' }],
    ['monthly 31', { repeat: 'monthly', time: '06:00', on: { day: 31 } },
      { kind: 'calendar', timezone: TZ, rrule: 'FREQ=MONTHLY;BYMONTHDAY=28,29,30,31;BYSETPOS=-1;BYHOUR=6;BYMINUTE=0' }],
    ['last day', { repeat: 'monthly', time: '23:59', on: { lastDay: true } },
      { kind: 'calendar', timezone: TZ, rrule: 'FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=23;BYMINUTE=59' }],
    ['last Friday', { repeat: 'monthly', time: '09:00', on: { nth: -1, weekday: 'FR' } },
      { kind: 'calendar', timezone: TZ, rrule: 'FREQ=MONTHLY;BYDAY=-1FR;BYHOUR=9;BYMINUTE=0' }],
    ['second Tuesday', { repeat: 'monthly', time: '09:00', on: { nth: 2, weekday: 'TU' } },
      { kind: 'calendar', timezone: TZ, rrule: 'FREQ=MONTHLY;BYDAY=2TU;BYHOUR=9;BYMINUTE=0' }],
    ['once', { repeat: 'once', date: '2026-12-24', time: '08:05' }, { kind: 'once', timezone: TZ, at: '2026-12-24T08:05' }],
  ]
  it.each(cases)('%s', (_n, rule, spec) => {
    expect(compilePickerRule(rule, TZ)).toEqual(spec)
  })

  it('never emits a 6-field cron or a DTSTART', () => {
    for (const [, rule] of cases) {
      const s = compilePickerRule(rule, TZ)
      if (s.kind === 'cron') expect(s.cron.split(' ')).toHaveLength(5)
      if (s.kind === 'calendar') expect(s.rrule).not.toMatch(/DTSTART/)
    }
  })

  it('treats a weekly rule with no/all days as every day', () => {
    expect(compilePickerRule({ repeat: 'weekly', time: '09:00', days: [] }, TZ)).toMatchObject({ cron: '0 9 * * *' })
    expect(compilePickerRule({ repeat: 'weekly', time: '09:00', days: [...WEEKDAYS] }, TZ)).toMatchObject({ cron: '0 9 * * *' })
  })
})

describe('parseSpecToRule', () => {
  it('round-trips every compiled shape', () => {
    const rules: PickerRule[] = [
      { repeat: 'minutes', every: 10 },
      { repeat: 'minutes', every: 20, window: { from: '08:00', to: '18:00' }, days: ['MO', 'WE'] },
      { repeat: 'hourly', minute: 45 },
      { repeat: 'daily', time: '09:00', weekdaysOnly: false },
      { repeat: 'daily', time: '09:00', weekdaysOnly: true },
      { repeat: 'weekly', time: '17:15', days: ['MO', 'WE', 'FR'] },
      { repeat: 'weekly', time: '17:15', days: ['SA', 'SU'] },
      { repeat: 'monthly', time: '03:00', on: { day: 15 } },
      { repeat: 'monthly', time: '03:00', on: { day: 29 } },
      { repeat: 'monthly', time: '03:00', on: { day: 30 } },
      { repeat: 'monthly', time: '03:00', on: { day: 31 } },
      { repeat: 'monthly', time: '03:00', on: { lastDay: true } },
      { repeat: 'monthly', time: '03:00', on: { nth: 1, weekday: 'MO' } },
      { repeat: 'monthly', time: '03:00', on: { nth: 4, weekday: 'TH' } },
      { repeat: 'monthly', time: '03:00', on: { nth: -1, weekday: 'FR' } },
      { repeat: 'once', date: '2027-01-02', time: '04:30' },
    ]
    for (const rule of rules) expect(parseSpecToRule(compilePickerRule(rule, TZ))).toEqual(rule)
  })

  it('reads Mon-Fri as weekdays, the canonical form', () => {
    const weekly: PickerRule = { repeat: 'weekly', time: '09:00', days: ['MO', 'TU', 'WE', 'TH', 'FR'] }
    expect(parseSpecToRule(compilePickerRule(weekly, TZ))).toEqual({ repeat: 'daily', time: '09:00', weekdaysOnly: true })
  })

  it('reads an existing routine cron (Sunday as 7 included)', () => {
    expect(parseSpecToRule(cron('0 9 * * 1-5'))).toEqual({ repeat: 'daily', time: '09:00', weekdaysOnly: true })
    expect(parseSpecToRule(cron('0 9 * * 7'))).toEqual({ repeat: 'weekly', time: '09:00', days: ['SU'] })
    expect(parseSpecToRule(cron('  30   2 * * *  '))).toEqual({ repeat: 'daily', time: '02:30', weekdaysOnly: false })
  })

  it.each([
    ['6-field cron', '0 0 9 * * 1-5'],
    ['4-field cron', '0 9 * *'],
    ['L extension', '0 9 L * *'],
    ['5L weekday extension', '0 9 * * 5L'],
    ['nth extension', '0 9 * * 1#2'],
    ['W extension', '0 9 15W * *'],
    ['day 29 as plain cron', '0 9 29 * *'],
    ['specific month', '0 9 1 6 *'],
    ['month-restricted daily', '0 9 * 6 *'],
    ['odd step', '*/7 * * * *'],
    ['hour list', '0 9,17 * * *'],
    ['hourly with weekdays', '5 * * * 1-5'],
    ['macro', '@daily'],
    ['garbage', 'not a cron'],
    ['out of range', '61 9 * * *'],
  ])('cron %s → null (Custom schedule)', (_n, c) => {
    expect(parseSpecToRule(cron(c))).toBeNull()
  })

  it.each([
    ['weekly freq', 'FREQ=WEEKLY;BYDAY=MO;BYHOUR=9;BYMINUTE=0'],
    ['DTSTART present', 'DTSTART=20260101T000000;FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=9;BYMINUTE=0'],
    ['no time', 'FREQ=MONTHLY;BYMONTHDAY=-1'],
    ['two weekdays', 'FREQ=MONTHLY;BYDAY=1MO,1TU;BYHOUR=9;BYMINUTE=0'],
    ['fifth weekday', 'FREQ=MONTHLY;BYDAY=5MO;BYHOUR=9;BYMINUTE=0'],
    ['extra COUNT', 'FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=3;BYHOUR=9;BYMINUTE=0'],
    ['gappy day set', 'FREQ=MONTHLY;BYMONTHDAY=29,31;BYSETPOS=-1;BYHOUR=9;BYMINUTE=0'],
    ['garbage', 'banana'],
  ])('calendar %s → null', (_n, r) => {
    expect(parseSpecToRule(cal(r))).toBeNull()
  })

  it('once: malformed at → null', () => {
    expect(parseSpecToRule({ kind: 'once', timezone: 'UTC', at: 'tomorrow' })).toBeNull()
    expect(parseSpecToRule({ kind: 'once', timezone: 'UTC', at: '2026-12-24T08:05' })).toEqual(
      { repeat: 'once', date: '2026-12-24', time: '08:05' })
  })
})

describe('24:00 is a window end, never a time of day (#18432 review)', () => {
  it('splitTime accepts 24:00 only as an end of day', () => {
    expect(splitTime('24:00')).toBeNull()
    expect(splitTime('24:00', true)).toEqual([24, 0])
    expect(splitTime('24:30', true)).toBeNull()
    expect(splitTime('23:59')).toEqual([23, 59])
  })

  it('rejects a one-off at T24:00 on import, and computes no run for it', () => {
    const spec: ScheduleSpec = { kind: 'once', timezone: 'UTC', at: '2030-01-02T24:00' }
    expect(parseSpecToRule(spec)).toBeNull()
    expect(nextRuns(spec, 3, new Date('2030-01-01T00:00:00Z'))).toBeNull()
  })

  it('still compiles a minutes window ending at 24:00', () => {
    const spec = compilePickerRule({ repeat: 'minutes', every: 5, window: { from: '20:00', to: '24:00' } }, 'UTC')
    expect(spec).toMatchObject({ kind: 'cron', cron: '*/5 20-23 * * *' })
  })
})

describe('day fields combine as croniter combines them (#18432 review)', () => {
  it('a stepped day-of-month is restricted, so it is ORed with the weekday', () => {
    // croniter, the backend scheduler, for "0 9 */2 * MON" from Tue 1 Jan 2030:
    // Tue 01, Thu 03, Sat 05, Mon 07, Wed 09, Fri 11, Sun 13, Mon 14.
    const spec: ScheduleSpec = { kind: 'cron', timezone: 'UTC', cron: '0 9 */2 * MON' }
    const runs = nextRuns(spec, 8, new Date('2030-01-01T00:00:00Z'))!
    expect(runs.map((d) => d.getUTCDate())).toEqual([1, 3, 5, 7, 9, 11, 13, 14])
  })
})

describe('summaryKeys', () => {
  it('derives a key and language-neutral params, never cron', () => {
    expect(summaryKeys({ repeat: 'daily', time: '09:00', weekdaysOnly: true })).toEqual(
      { key: 'schedule.summary.dailyWeekdays', params: { time: '09:00' } })
    expect(summaryKeys({ repeat: 'minutes', every: 15, window: { from: '08:00', to: '18:00' }, days: ['MO', 'TU', 'WE', 'TH', 'FR'] }).key)
      .toBe('schedule.summary.minutesWindowWeekdays')
    expect(summaryKeys({ repeat: 'minutes', every: 15, days: ['MO', 'WE'] })).toEqual(
      { key: 'schedule.summary.minutesDays', params: { every: 15, days: ['MO', 'WE'] } })
    expect(summaryKeys({ repeat: 'monthly', time: '09:00', on: { nth: -1, weekday: 'FR' } })).toEqual(
      { key: 'schedule.summary.monthlyNthLast', params: { weekday: 'FR', time: '09:00' } })
    expect(summaryKeys({ repeat: 'monthly', time: '09:00', on: { nth: 2, weekday: 'TU' } }).key)
      .toBe('schedule.summary.monthlyNth2')
    expect(summaryKeys({ repeat: 'monthly', time: '09:00', on: { lastDay: true } }).key).toBe('schedule.summary.monthlyLastDay')
    expect(summaryKeys({ repeat: 'once', date: '2026-12-24', time: '08:00' }).params).toEqual({ date: '2026-12-24', time: '08:00' })
  })

  it('collapses a weekly rule of all/Mon-Fri days to the daily summaries', () => {
    expect(summaryKeys({ repeat: 'weekly', time: '09:00', days: [...WEEKDAYS] }).key).toBe('schedule.summary.daily')
    expect(summaryKeys({ repeat: 'weekly', time: '09:00', days: ['FR', 'MO', 'TU', 'WE', 'TH'] }).key)
      .toBe('schedule.summary.dailyWeekdays')
    expect(summaryKeys({ repeat: 'weekly', time: '09:00', days: ['FR', 'MO'] }).params.days).toEqual(['MO', 'FR'])
  })

  it('summaryText resolves weekdays via Intl and appends the zone; null → custom', () => {
    const t = (k: string, p?: Record<string, unknown>) => `${k}|${JSON.stringify(p ?? {})}`
    const text = summaryText({ repeat: 'weekly', time: '09:00', days: ['MO', 'FR'] }, 'Z', t, 'en')
    expect(text).toContain('schedule.summary.weekly|{\\"days\\":\\"Monday and Friday\\",\\"time\\":\\"09:00\\"}')
    expect(text).toContain('"zone":"Z"')
    expect(summaryText(null, 'Z', t, 'en')).toBe('schedule.summary.custom|{}')
  })
})
