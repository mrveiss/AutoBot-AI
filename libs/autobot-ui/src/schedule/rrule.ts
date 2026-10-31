// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// RFC 5545 RRULE body reading for the calendar subset the picker emits.

import { WEEKDAYS, type Weekday } from './types'

export type RruleParts = Record<string, string>

/** "K=V;K=V" → parts; null on DTSTART, a duplicate key, or a malformed part. */
export function parseRruleParts(body: string): RruleParts | null {
  const parts: RruleParts = {}
  for (const piece of body.trim().replace(/^RRULE:/i, '').split(';')) {
    const m = /^([A-Za-z]+)=(.+)$/.exec(piece)
    if (!m) return null
    const key = m[1].toUpperCase()
    if (key === 'DTSTART' || key in parts) return null
    parts[key] = m[2]
  }
  return parts
}

export interface DayToken {
  /** 0 = every such weekday in the period; else the nth (negative from end). */
  ordinal: number
  weekday: Weekday
}

export function parseByDay(text: string): DayToken[] | null {
  const out: DayToken[] = []
  for (const token of text.split(',')) {
    const m = /^([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)$/.exec(token)
    if (!m) return null
    out.push({ ordinal: m[1] ? Number(m[1]) : 0, weekday: m[2] as Weekday })
  }
  return out.length ? out : null
}

export function parseIntList(text: string | undefined, lo: number, hi: number): number[] | null {
  // 0 is a valid hour/minute but never a valid BYMONTHDAY/BYSETPOS (lo < 0 ⇒ signed list)
  if (text === undefined) return null
  const out = text.split(',').map((t) => (/^[+-]?\d+$/.test(t) ? Number(t) : NaN))
  const ok = out.length > 0 && out.every((n) => Number.isInteger(n) && n >= lo && n <= hi && (lo >= 0 || n !== 0))
  return ok ? out : null
}

export function isWeekday(value: string): value is Weekday {
  return (WEEKDAYS as readonly string[]).includes(value)
}
