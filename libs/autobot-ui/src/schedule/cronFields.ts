// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Standard 5-field cron field parsing — shared by parseSpecToRule and the
// advisory nextRuns so the two can never read a cron differently. Extensions
// (L, W, #, ?, 6th field, @macros) are NOT standard and parse to null.

export interface CronFields {
  minute: Set<number>
  hour: Set<number>
  dom: Set<number>
  month: Set<number>
  dow: Set<number>
  /** The field text began with "*" — decides Vixie dom/dow AND-vs-OR. */
  domStar: boolean
  dowStar: boolean
  raw: string[]
}

const MONTH_NAMES = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const DOW_NAMES = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']

function toNumber(token: string, names: string[] | undefined, offset: number): number | null {
  if (/^\d+$/.test(token)) return Number(token)
  const idx = names ? names.indexOf(token.toUpperCase()) : -1
  return idx >= 0 ? idx + offset : null
}

function parseRange(
  part: string, min: number, max: number, names: string[] | undefined, offset: number,
): number[] | null {
  const [body, stepText, extra] = part.split('/')
  if (extra !== undefined || (stepText !== undefined && !/^[1-9]\d*$/.test(stepText))) return null
  const step = stepText === undefined ? 1 : Number(stepText)
  let lo: number | null = min
  let hi: number | null = max
  if (body !== '*') {
    const [a, b, more] = body.split('-')
    if (more !== undefined) return null
    lo = toNumber(a, names, offset)
    hi = b === undefined ? (stepText === undefined ? lo : max) : toNumber(b, names, offset)
  }
  if (lo === null || hi === null || lo < min || hi > max || lo > hi) return null
  const out: number[] = []
  for (let v = lo; v <= hi; v += step) out.push(v)
  return out
}

/** One cron field → the set of values, or null if invalid / non-standard. */
export function parseCronField(
  field: string, min: number, max: number, names?: string[], offset = 0,
): Set<number> | null {
  const out = new Set<number>()
  for (const part of field.split(',')) {
    const values = parseRange(part, min, max, names, offset)
    if (!values) return null
    values.forEach((v) => out.add(v))
  }
  return out
}

function parseDow(field: string): Set<number> | null {
  const raw = parseCronField(field, 0, 7, DOW_NAMES, 0)
  if (!raw) return null
  return new Set([...raw].map((v) => v % 7))
}

/** Parse exactly five whitespace-separated fields; null for anything else. */
export function parseCron5(cron: string): CronFields | null {
  const raw = cron.trim().split(/\s+/)
  if (raw.length !== 5) return null
  const minute = parseCronField(raw[0], 0, 59)
  const hour = parseCronField(raw[1], 0, 23)
  const dom = parseCronField(raw[2], 1, 31)
  const month = parseCronField(raw[3], 1, 12, MONTH_NAMES, 1)
  const dow = parseDow(raw[4])
  if (!minute || !hour || !dom || !month || !dow) return null
  // Only a literal `*` is unrestricted: croniter (the backend scheduler) ORs a stepped `*/2`
  // with the weekday like any other restricted day field.
  return { minute, hour, dom, month, dow, domStar: raw[2] === '*', dowStar: raw[4] === '*', raw }
}
