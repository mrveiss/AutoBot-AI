// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// IANA-zone wall-clock arithmetic on top of Intl only (no dependency). The
// zone database ships with the runtime, so DST rules are the platform's.

const cache = new Map<string, Intl.DateTimeFormat>()
const DAY_MS = 86_400_000

export interface LocalParts {
  y: number
  m: number
  d: number
  h: number
  mi: number
}

function formatter(zone: string): Intl.DateTimeFormat {
  let f = cache.get(zone)
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone: zone, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric',
      hour: 'numeric', minute: 'numeric', second: 'numeric',
    })
    cache.set(zone, f)
  }
  return f
}

export function isValidZone(zone: string): boolean {
  try {
    formatter(zone)
    return true
  } catch {
    return false
  }
}

export function localParts(ms: number, zone: string): LocalParts {
  const v: Record<string, number> = {}
  for (const p of formatter(zone).formatToParts(new Date(ms))) {
    if (p.type !== 'literal') v[p.type] = Number(p.value)
  }
  return { y: v.year, m: v.month, d: v.day, h: v.hour, mi: v.minute }
}

/** Zone offset from UTC at an instant, in ms (local − UTC). */
export function zoneOffsetMs(ms: number, zone: string): number {
  const v: Record<string, number> = {}
  for (const p of formatter(zone).formatToParts(new Date(ms))) {
    if (p.type !== 'literal') v[p.type] = Number(p.value)
  }
  const wall = Date.UTC(v.year, v.month - 1, v.day, v.hour, v.minute, v.second)
  return wall - Math.floor(ms / 1000) * 1000
}

/**
 * Wall-clock time in `zone` → UTC ms. Ambiguous time (clocks go back) takes
 * the EARLIER instant. A time that does not exist (clocks go forward) is
 * shifted forward by the gap — advisory; the server is authoritative.
 */
export function localToUtc(p: LocalParts, zone: string): number {
  const wall = Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi)
  const before = zoneOffsetMs(wall - DAY_MS, zone)
  const after = zoneOffsetMs(wall + DAY_MS, zone)
  const valid = [before, after]
    .map((off) => ({ off, t: wall - off }))
    .filter(({ off, t }) => zoneOffsetMs(t, zone) === off)
    .map(({ t }) => t)
  return valid.length ? Math.min(...valid) : wall - before
}

/** `Intl.supportedValuesOf` is ES2022; the SLM frontend compiles the kit against an older `lib`. */
type IntlWithZones = typeof Intl & { supportedValuesOf?: (key: 'timeZone') => string[] }

/** Selectable IANA zones, always including `include` and UTC. */
export function listZones(...include: string[]): string[] {
  const all = (Intl as IntlWithZones).supportedValuesOf?.('timeZone') ?? []
  return [...new Set([...include.filter(Boolean), 'UTC', ...all])].sort((a, b) => a.localeCompare(b))
}

/** Calendar date "YYYY-MM-DD" of `ms` in `zone`, shifted by `plusDays`. */
export function zoneDate(ms: number, zone: string, plusDays = 0): string {
  const p = localParts(ms, zone)
  const d = new Date(Date.UTC(p.y, p.m - 1, p.d + plusDays))
  return d.toISOString().slice(0, 10)
}
