// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Small shared helpers for LocalTime and the cron/RRULE weekday numbering.

import { WEEKDAYS, type LocalTime, type Weekday } from './types'

export function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/**
 * "HH:MM" → [h, m]; null when malformed or out of range. "24:00" is accepted only
 * with `endOfDay` -- a minutes window's end (types.ts) -- never as a time of day,
 * where it would reach localToUtc as hour 24.
 */
export function splitTime(time: LocalTime, endOfDay = false): [number, number] | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(time)
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h === 24 && min === 0) return endOfDay ? [24, 0] : null
  return h < 24 && min <= 59 ? [h, min] : null
}

export function joinTime(h: number, m: number): LocalTime {
  return `${pad2(h)}:${pad2(m)}`
}

/** Cron weekday number: SU=0, MO=1 … SA=6. */
export function weekdayToCron(day: Weekday): number {
  return (WEEKDAYS.indexOf(day) + 1) % 7
}

export function cronToWeekday(n: number): Weekday {
  return WEEKDAYS[(n + 6) % 7]
}

/** Unique weekdays in Monday-first order. */
export function sortDays(days: readonly Weekday[]): Weekday[] {
  return WEEKDAYS.filter((d) => days.includes(d))
}

/** Calendar date → cron weekday (0=Sun) — independent of any timezone. */
export function dayOfWeek(y: number, m: number, d: number): number {
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay()
}

export function daysInMonth(y: number, m: number): number {
  return new Date(Date.UTC(y, m, 0)).getUTCDate()
}
