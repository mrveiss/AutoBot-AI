// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Schedule contract (#18432): the ONE stored shape (ScheduleSpec) and the
// UI-only state the picker edits (PickerRule). Summaries are derived from a
// rule, never stored. Pure types — no Vue, no strings.

export type IanaZone = string
/** "HH:MM", 24h, in the spec's timezone ("24:00" only as a window end). */
export type LocalTime = string
/** RFC 5545 spelling. */
export type Weekday = 'MO' | 'TU' | 'WE' | 'TH' | 'FR' | 'SA' | 'SU'

export const WEEKDAYS: readonly Weekday[] = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
export const MINUTE_STEPS = [5, 10, 15, 20, 30] as const
export type MinuteStep = (typeof MINUTE_STEPS)[number]
export type Nth = 1 | 2 | 3 | 4 | -1

export type ScheduleSpec =
  | { kind: 'cron'; timezone: IanaZone; cron: string }
  | { kind: 'calendar'; timezone: IanaZone; rrule: string }
  | { kind: 'once'; timezone: IanaZone; at: string }

export type MonthlyOn = { day: number } | { lastDay: true } | { nth: Nth; weekday: Weekday }

export type PickerRule =
  | { repeat: 'minutes'; every: MinuteStep; window?: { from: LocalTime; to: LocalTime }; days?: Weekday[] }
  | { repeat: 'hourly'; minute: number }
  | { repeat: 'daily'; time: LocalTime; weekdaysOnly: boolean }
  | { repeat: 'weekly'; time: LocalTime; days: Weekday[] }
  | { repeat: 'monthly'; time: LocalTime; on: MonthlyOn }
  | { repeat: 'once'; date: string; time: LocalTime }

export type RepeatKind = PickerRule['repeat']

/** Body of POST /api/schedules/preview — the server is the source of truth. */
export interface PreviewResult {
  valid: boolean
  error_code?: string
  error_params?: Record<string, unknown>
  /** ISO-8601 with offset. */
  next_runs: string[]
  kind?: ScheduleSpec['kind']
}

/**
 * App-supplied server preview. Resolve `null` when the endpoint is
 * unavailable (the picker keeps working on its advisory client preview).
 */
export type SchedulePreviewFn = (spec: ScheduleSpec, count: number) => Promise<PreviewResult | null>

/** App-supplied translator; the kit owns keys, never strings. */
export type ScheduleTranslate = (key: string, params?: Record<string, unknown>) => string

export const DEFAULT_TIME: LocalTime = '09:00'
