// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// ScheduleSpec → PickerRule (#18432). null means "Custom schedule": the spec
// is valid but not something the picker can show as clicks. The cron path is
// the inverse of compile.ts; both read cron through cronFields.ts.

import { parseCron5, type CronFields } from './cronFields'
import { parseByDay, parseRruleParts, type RruleParts } from './rrule'
import { cronToWeekday, joinTime, sortDays } from './time'
import { MINUTE_STEPS, type MinuteStep, type Nth, type PickerRule, type ScheduleSpec } from './types'

const only = (s: Set<number>): number | null => (s.size === 1 ? [...s][0] : null)
const isMonToFri = (s: Set<number>): boolean => s.size === 5 && [1, 2, 3, 4, 5].every((d) => s.has(d))
const isStar = (raw: string): boolean => raw === '*'

function everyStep(raw: string): MinuteStep | null {
  const m = /^\*\/(\d+)$/.exec(raw)
  const n = m ? Number(m[1]) : NaN
  return (MINUTE_STEPS as readonly number[]).includes(n) ? (n as MinuteStep) : null
}

function hourWindow(raw: string): { from: string; to: string } | null | undefined {
  if (isStar(raw)) return undefined
  const m = /^(\d{1,2})-(\d{1,2})$/.exec(raw)
  if (!m || Number(m[1]) > Number(m[2])) return null
  return { from: joinTime(Number(m[1]), 0), to: joinTime(Number(m[2]) + 1, 0) }
}

function minutesRule(f: CronFields): PickerRule | null {
  const every = everyStep(f.raw[0])
  const window = hourWindow(f.raw[1])
  if (!every || window === null || !isStar(f.raw[2]) || !isStar(f.raw[3])) return null
  const days = isStar(f.raw[4]) ? undefined : sortDays([...f.dow].map(cronToWeekday))
  return { repeat: 'minutes', every, ...(window ? { window } : {}), ...(days ? { days } : {}) }
}

function timedRule(f: CronFields, minute: number, hour: number): PickerRule | null {
  const time = joinTime(hour, minute)
  if (isStar(f.raw[2]) && isStar(f.raw[3])) {
    if (isStar(f.raw[4]) || f.dow.size === 7) return { repeat: 'daily', time, weekdaysOnly: false }
    if (isMonToFri(f.dow)) return { repeat: 'daily', time, weekdaysOnly: true }
    if (/^[\d,-]+$/.test(f.raw[4])) return { repeat: 'weekly', time, days: sortDays([...f.dow].map(cronToWeekday)) }
    return null
  }
  const day = /^\d+$/.test(f.raw[2]) ? only(f.dom) : null
  if (day !== null && day <= 28 && isStar(f.raw[3]) && isStar(f.raw[4])) {
    return { repeat: 'monthly', time, on: { day } }
  }
  return null
}

function parseCronRule(cron: string): PickerRule | null {
  const f = parseCron5(cron)
  if (!f) return null
  const [minute, hour] = [only(f.minute), only(f.hour)]
  if (f.raw[0].startsWith('*/')) return minutesRule(f)
  if (minute === null || !/^\d+$/.test(f.raw[0])) return null
  if (isStar(f.raw[1]) && f.raw.slice(2).every(isStar)) return { repeat: 'hourly', minute }
  if (hour === null || !/^\d+$/.test(f.raw[1])) return null
  return timedRule(f, minute, hour)
}

function rruleTimeOf(p: RruleParts): string | null {
  if (!/^\d{1,2}$/.test(p.BYHOUR ?? '') || !/^\d{1,2}$/.test(p.BYMINUTE ?? '')) return null
  const [h, m] = [Number(p.BYHOUR), Number(p.BYMINUTE)]
  return h < 24 && m < 60 ? joinTime(h, m) : null
}

function monthlyOn(p: RruleParts): Extract<PickerRule, { repeat: 'monthly' }>['on'] | null {
  const keys = Object.keys(p).filter((k) => !['FREQ', 'BYHOUR', 'BYMINUTE'].includes(k)).sort().join()
  if (keys === 'BYMONTHDAY' && p.BYMONTHDAY === '-1') return { lastDay: true }
  if (keys === 'BYDAY') {
    const tokens = parseByDay(p.BYDAY)
    const nth = tokens && tokens.length === 1 ? tokens[0].ordinal : 0
    return [1, 2, 3, 4, -1].includes(nth) ? { nth: nth as Nth, weekday: tokens![0].weekday } : null
  }
  if (keys === 'BYMONTHDAY,BYSETPOS' && p.BYSETPOS === '-1') {
    const days = p.BYMONTHDAY.split(',').map(Number)
    const last = days[days.length - 1]
    const expect = Array.from({ length: last - 27 }, (_, i) => 28 + i)
    return last >= 29 && last <= 31 && days.join() === expect.join() ? { day: last } : null
  }
  return null
}

function parseCalendarRule(rrule: string): PickerRule | null {
  const p = parseRruleParts(rrule)
  const time = p ? rruleTimeOf(p) : null
  if (!p || !time || p.FREQ !== 'MONTHLY') return null
  const on = monthlyOn(p)
  return on ? { repeat: 'monthly', time, on } : null
}

function parseOnce(at: string): PickerRule | null {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})$/.exec(at)
  return m ? { repeat: 'once', date: m[1], time: m[2] } : null
}

export function parseSpecToRule(spec: ScheduleSpec): PickerRule | null {
  if (spec.kind === 'once') return parseOnce(spec.at)
  if (spec.kind === 'calendar') return parseCalendarRule(spec.rrule)
  return parseCronRule(spec.cron)
}
