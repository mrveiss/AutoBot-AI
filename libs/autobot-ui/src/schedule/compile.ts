// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// PickerRule → ScheduleSpec (#18432). Picks the simplest kind that fits:
// 5-field cron when it expresses the rule exactly, an RFC 5545 rule for the
// monthly shapes cron cannot (day 29–31, last day, nth/last weekday), and
// `once` for one-off runs.

import { pad2, splitTime, weekdayToCron } from './time'
import type { MonthlyOn, PickerRule, ScheduleSpec, Weekday } from './types'

/** Cron day-of-week field: "*" for none/all, else compressed numbers. */
export function cronDays(days: readonly Weekday[] | undefined): string {
  const nums = [...new Set((days ?? []).map(weekdayToCron))].sort((a, b) => a - b)
  if (nums.length === 0 || nums.length === 7) return '*'
  const out: string[] = []
  for (let i = 0; i < nums.length; ) {
    let j = i
    while (j + 1 < nums.length && nums[j + 1] === nums[j] + 1) j++
    out.push(j - i >= 2 ? `${nums[i]}-${nums[j]}` : nums.slice(i, j + 1).join(','))
    i = j + 1
  }
  return out.join(',')
}

function hm(time: string): [number, number] {
  return splitTime(time) ?? [0, 0]
}

function cronHours(window: { from: string; to: string } | undefined): string {
  if (!window) return '*'
  const from = hm(window.from)[0]
  const toExclusive = (splitTime(window.to, true) ?? [0])[0] || 24
  const last = Math.min(23, Math.max(from, toExclusive - 1))
  return from === 0 && last === 23 ? '*' : `${from}-${last}`
}

function rruleTime(time: string): string {
  const [h, m] = hm(time)
  return `BYHOUR=${h};BYMINUTE=${m}`
}

function monthlyRrule(on: MonthlyOn, time: string): string {
  const t = rruleTime(time)
  if ('lastDay' in on) return `FREQ=MONTHLY;BYMONTHDAY=-1;${t}`
  if ('nth' in on) return `FREQ=MONTHLY;BYDAY=${on.nth}${on.weekday};${t}`
  const days = Array.from({ length: on.day - 27 }, (_, i) => 28 + i).join(',')
  return `FREQ=MONTHLY;BYMONTHDAY=${days};BYSETPOS=-1;${t}`
}

function compileMonthly(rule: Extract<PickerRule, { repeat: 'monthly' }>, tz: string): ScheduleSpec {
  const { on, time } = rule
  if ('day' in on && on.day >= 1 && on.day <= 28) {
    const [h, m] = hm(time)
    return { kind: 'cron', timezone: tz, cron: `${m} ${h} ${on.day} * *` }
  }
  const safe: MonthlyOn = 'day' in on ? { day: Math.min(31, Math.max(29, on.day)) } : on
  return { kind: 'calendar', timezone: tz, rrule: monthlyRrule(safe, time) }
}

type CronRule = Exclude<PickerRule, { repeat: 'once' | 'monthly' }>

function compileCron(rule: CronRule): string {
  switch (rule.repeat) {
    case 'minutes':
      return `*/${rule.every} ${cronHours(rule.window)} * * ${cronDays(rule.days)}`
    case 'hourly':
      return `${rule.minute} * * * *`
    case 'daily': {
      const [h, m] = hm(rule.time)
      return `${m} ${h} * * ${rule.weekdaysOnly ? '1-5' : '*'}`
    }
    case 'weekly': {
      const [h, m] = hm(rule.time)
      return `${m} ${h} * * ${cronDays(rule.days)}`
    }
  }
}

export function compilePickerRule(rule: PickerRule, timezone: string): ScheduleSpec {
  if (rule.repeat === 'once') {
    const [h, m] = hm(rule.time)
    return { kind: 'once', timezone, at: `${rule.date}T${pad2(h)}:${pad2(m)}` }
  }
  if (rule.repeat === 'monthly') return compileMonthly(rule, timezone)
  return { kind: 'cron', timezone, cron: compileCron(rule) }
}
