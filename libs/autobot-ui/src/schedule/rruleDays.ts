// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Expansion of the MONTHLY RRULE subset (BYMONTH, BYMONTHDAY, BYDAY with
// optional ordinal, BYSETPOS, BYHOUR, BYMINUTE) into the days of one month.
// Any other part returns null: this is advisory, the server expands for real.

import { parseByDay, parseIntList, parseRruleParts, type DayToken } from './rrule'
import { dayOfWeek, daysInMonth, weekdayToCron } from './time'

const SUPPORTED = ['FREQ', 'INTERVAL', 'BYMONTH', 'BYMONTHDAY', 'BYDAY', 'BYSETPOS', 'BYHOUR', 'BYMINUTE']

export interface MonthlyRule {
  days: (y: number, m: number) => number[]
  hours: number[]
  minutes: number[]
}

function byMonthDay(list: number[] | null, y: number, m: number): number[] {
  const dim = daysInMonth(y, m)
  return (list ?? []).map((v) => (v > 0 ? v : dim + 1 + v)).filter((d) => d >= 1 && d <= dim)
}

function byDay(tokens: DayToken[], y: number, m: number): number[] {
  const dim = daysInMonth(y, m)
  const out: number[] = []
  for (const { ordinal, weekday } of tokens) {
    const hits = Array.from({ length: dim }, (_, i) => i + 1).filter(
      (d) => dayOfWeek(y, m, d) === weekdayToCron(weekday),
    )
    if (ordinal === 0) out.push(...hits)
    else {
      const pick = ordinal > 0 ? hits[ordinal - 1] : hits[hits.length + ordinal]
      if (pick !== undefined) out.push(pick)
    }
  }
  return out
}

function setPos(days: number[], positions: number[]): number[] {
  const picked = positions.map((p) => (p > 0 ? days[p - 1] : days[days.length + p]))
  return picked.filter((d) => d !== undefined)
}

interface Parsed {
  dayList: number[] | null
  tokens: DayToken[] | null
  months: number[] | null
  pos: number[] | null
}

function expandMonth(q: Parsed, y: number, m: number): number[] {
  if (q.months && !q.months.includes(m)) return []
  const a = q.dayList ? byMonthDay(q.dayList, y, m) : null
  const b = q.tokens ? byDay(q.tokens, y, m) : null
  const merged = a && b ? a.filter((d) => b.includes(d)) : (a ?? b ?? [])
  const set = [...new Set(merged)].sort((x, z) => x - z)
  return q.pos ? setPos(set, q.pos).sort((x, z) => x - z) : set
}

/** Present-but-unparseable → 'bad'; absent → null. */
function optional<T>(text: string | undefined, read: (t: string) => T | null): T | null | 'bad' {
  if (text === undefined) return null
  return read(text) ?? 'bad'
}

function readParsed(p: Record<string, string>): Parsed | null {
  const dayList = optional(p.BYMONTHDAY, (t) => parseIntList(t, -31, 31))
  const tokens = optional(p.BYDAY, parseByDay)
  const months = optional(p.BYMONTH, (t) => parseIntList(t, 1, 12))
  const pos = optional(p.BYSETPOS, (t) => parseIntList(t, -366, 366))
  if ([dayList, tokens, months, pos].includes('bad') || (!dayList && !tokens)) return null
  return { dayList, tokens, months, pos } as Parsed
}

export function monthDaysFromRrule(rrule: string): MonthlyRule | null {
  const p = parseRruleParts(rrule)
  if (!p || p.FREQ !== 'MONTHLY' || (p.INTERVAL ?? '1') !== '1') return null
  if (Object.keys(p).some((k) => !SUPPORTED.includes(k))) return null
  const hours = parseIntList(p.BYHOUR, 0, 23)
  const minutes = parseIntList(p.BYMINUTE, 0, 59)
  const parsed = readParsed(p)
  if (!hours || !minutes || !parsed) return null
  return { days: (y, m) => expandMonth(parsed, y, m), hours, minutes }
}
