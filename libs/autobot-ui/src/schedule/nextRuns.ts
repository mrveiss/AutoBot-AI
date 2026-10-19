// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Advisory next-run preview (#18432). The server (POST /api/schedules/preview,
// the same code the scheduler runs) is the source of truth; this exists so the
// picker shows something instantly and offline. It covers 5-field cron, the
// MONTHLY calendar subset the picker emits, and `once`. Anything it cannot
// compute EXACTLY returns null — never a guess. DST is handled with the spec's
// IANA zone via Intl (zone.ts).

import { parseCron5 } from './cronFields'
import { monthDaysFromRrule } from './rruleDays'
import { daysInMonth, dayOfWeek, splitTime } from './time'
import type { ScheduleSpec } from './types'
import { isValidZone, localParts, localToUtc } from './zone'

const MAX_MONTHS = 12 * 9
type DaysOfMonth = (y: number, m: number) => number[]
type Time = [number, number]

function cronSource(cron: string): { days: DaysOfMonth; times: Time[] } | null {
  const f = parseCron5(cron)
  if (!f) return null
  const days: DaysOfMonth = (y, m) => {
    if (!f.month.has(m)) return []
    const out: number[] = []
    for (let d = 1; d <= daysInMonth(y, m); d++) {
      const byDom = f.dom.has(d)
      const byDow = f.dow.has(dayOfWeek(y, m, d))
      if (f.domStar || f.dowStar ? byDom && byDow : byDom || byDow) out.push(d)
    }
    return out
  }
  return { days, times: timesOf([...f.hour], [...f.minute]) }
}

function timesOf(hours: number[], minutes: number[]): Time[] {
  const out: Time[] = []
  for (const h of [...hours].sort((a, b) => a - b)) {
    for (const m of [...minutes].sort((a, b) => a - b)) out.push([h, m])
  }
  return out
}

function calendarSource(rrule: string): { days: DaysOfMonth; times: Time[] } | null {
  const r = monthDaysFromRrule(rrule)
  return r ? { days: r.days, times: timesOf(r.hours, r.minutes) } : null
}

function collect(
  src: { days: DaysOfMonth; times: Time[] }, zone: string, count: number, after: Date,
): Date[] {
  const start = localParts(after.getTime(), zone)
  const out: number[] = []
  for (let i = 0; i < MAX_MONTHS && out.length < count; i++) {
    const idx = start.y * 12 + (start.m - 1) + i
    const [y, m] = [Math.floor(idx / 12), (idx % 12) + 1]
    for (const d of src.days(y, m)) {
      for (const [h, mi] of src.times) {
        const t = localToUtc({ y, m, d, h, mi }, zone)
        if (t > after.getTime()) out.push(t)
      }
      if (out.length >= count) break
    }
  }
  return out.sort((a, b) => a - b).slice(0, count).map((t) => new Date(t))
}

function onceRuns(at: string, zone: string, after: Date): Date[] | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})$/.exec(at)
  const time = m ? splitTime(m[4]) : null
  if (!m || !time) return null
  const t = localToUtc({ y: +m[1], m: +m[2], d: +m[3], h: time[0], mi: time[1] }, zone)
  return t > after.getTime() ? [new Date(t)] : []
}

/** Up to `count` upcoming runs after `after`, or null when not computable here. */
export function nextRuns(spec: ScheduleSpec, count: number, after: Date = new Date()): Date[] | null {
  if (!isValidZone(spec.timezone)) return null
  if (spec.kind === 'once') return onceRuns(spec.at, spec.timezone, after)
  const src = spec.kind === 'cron' ? cronSource(spec.cron) : calendarSource(spec.rrule)
  return src ? collect(src, spec.timezone, count, after) : null
}
