// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// PickerRule → i18n key + params (#18432). Derived, never stored. The kit owns
// the KEYS; the consuming app owns the strings (kit rule). Params carry
// language-neutral values (Weekday codes, "HH:MM", ISO date) that
// resolveSummaryParams turns into locale text via Intl.

import { sortDays } from './time'
import type { PickerRule, ScheduleTranslate, Weekday } from './types'

export type SummaryParams = Record<string, string | number | Weekday[] | Weekday>
export interface SummaryKey {
  key: string
  params: SummaryParams
}

const K = 'schedule.summary.'
const WEEKDAYS_SET = ['MO', 'TU', 'WE', 'TH', 'FR']

type DaysKind = 'all' | 'weekdays' | 'list'

function daysKind(days: readonly Weekday[] | undefined): DaysKind {
  const set = new Set(days ?? [])
  if (set.size === 0 || set.size === 7) return 'all'
  return set.size === 5 && WEEKDAYS_SET.every((d) => set.has(d as Weekday)) ? 'weekdays' : 'list'
}

function minutesKey(rule: Extract<PickerRule, { repeat: 'minutes' }>): SummaryKey {
  const kind = daysKind(rule.days)
  const params: SummaryParams = { every: rule.every }
  if (rule.window) Object.assign(params, { from: rule.window.from, to: rule.window.to })
  if (kind === 'list') params.days = sortDays(rule.days ?? [])
  const win = rule.window ? 'Window' : ''
  const suffix = kind === 'weekdays' ? 'Weekdays' : kind === 'list' ? 'Days' : ''
  return { key: `${K}minutes${win}${suffix}`, params }
}

function monthlyKey(rule: Extract<PickerRule, { repeat: 'monthly' }>): SummaryKey {
  const { on, time } = rule
  if ('day' in on) return { key: `${K}monthlyDay`, params: { day: on.day, time } }
  if ('lastDay' in on) return { key: `${K}monthlyLastDay`, params: { time } }
  const ord = on.nth === -1 ? 'Last' : String(on.nth)
  return { key: `${K}monthlyNth${ord}`, params: { weekday: on.weekday, time } }
}

function weeklyKey(rule: Extract<PickerRule, { repeat: 'weekly' }>): SummaryKey {
  const kind = daysKind(rule.days)
  if (kind === 'all') return { key: `${K}daily`, params: { time: rule.time } }
  if (kind === 'weekdays') return { key: `${K}dailyWeekdays`, params: { time: rule.time } }
  return { key: `${K}weekly`, params: { days: sortDays(rule.days), time: rule.time } }
}

export function summaryKeys(rule: PickerRule): SummaryKey {
  switch (rule.repeat) {
    case 'minutes':
      return minutesKey(rule)
    case 'hourly':
      return { key: `${K}hourly`, params: { minute: rule.minute } }
    case 'daily':
      return { key: `${K}${rule.weekdaysOnly ? 'dailyWeekdays' : 'daily'}`, params: { time: rule.time } }
    case 'weekly':
      return weeklyKey(rule)
    case 'monthly':
      return monthlyKey(rule)
    case 'once':
      return { key: `${K}once`, params: { date: rule.date, time: rule.time } }
  }
}

export const CUSTOM_SUMMARY_KEY = `${K}custom`

export function weekdayName(day: Weekday, locale: string, style: 'long' | 'short'): string {
  // 2024-01-01 was a Monday; MO..SU map to Jan 1..7.
  const index = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU'].indexOf(day)
  return new Intl.DateTimeFormat(locale, { weekday: style, timeZone: 'UTC' }).format(
    new Date(Date.UTC(2024, 0, 1 + index)),
  )
}

function formatDate(iso: string, locale: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, d)))
}

/** Turn language-neutral summary params into locale text via Intl. */
export function resolveSummaryParams(params: SummaryParams, locale: string): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const [name, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      const names = value.map((d) => weekdayName(d, locale, 'long'))
      out[name] = new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(names)
    } else if (name === 'weekday') out[name] = weekdayName(value as Weekday, locale, 'long')
    else if (name === 'date') out[name] = formatDate(String(value), locale)
    else out[name] = value as string | number
  }
  return out
}

/** Full sentence: rule summary + zone, e.g. "Every weekday at 09:00, company time". */
export function summaryText(
  rule: PickerRule | null, zoneLabel: string, t: ScheduleTranslate, locale: string,
): string {
  if (!rule) return t(CUSTOM_SUMMARY_KEY)
  const { key, params } = summaryKeys(rule)
  return t('schedule.summary.withZone', { summary: t(key, resolveSummaryParams(params, locale)), zone: zoneLabel })
}
