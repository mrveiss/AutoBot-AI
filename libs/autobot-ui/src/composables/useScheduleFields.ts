// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Per-repeat field bindings for SchedulePicker (#18432): narrowed views of
// the PickerRule plus the edits the template drives (window, day chips,
// monthly mode). One implementation; the SFC only renders.

import { computed, type Ref } from 'vue'
import { joinTime, splitTime } from '../schedule/time'
import type { PickerRule, RepeatKind, Weekday } from '../schedule/types'

type Of<R extends RepeatKind> = Extract<PickerRule, { repeat: R }>
export type MonthlyMode = 'day' | 'lastDay' | 'nth'

export function toggleDay(list: Weekday[] | undefined, day: Weekday, keepOne: boolean): Weekday[] {
  const cur = list ?? []
  if (cur.includes(day)) return keepOne && cur.length === 1 ? cur : cur.filter((d) => d !== day)
  return [...cur, day]
}

function narrow(rule: Ref<PickerRule | null>) {
  const pick = <R extends RepeatKind>(r: R) =>
    computed(() => (rule.value?.repeat === r ? (rule.value as Of<R>) : null))
  return {
    minutes: pick('minutes'), hourly: pick('hourly'), daily: pick('daily'),
    weekly: pick('weekly'), monthly: pick('monthly'), once: pick('once'),
  }
}

function windowFields(minutes: Ref<Of<'minutes'> | null>) {
  const windowOn = computed({
    get: () => !!minutes.value?.window,
    set: (on: boolean) => { if (minutes.value) minutes.value.window = on ? { from: '08:00', to: '18:00' } : undefined },
  })
  const hourOf = (key: 'from' | 'to'): number => {
    const w = minutes.value?.window
    return w ? ((splitTime(w[key], key === 'to') ?? [0])[0] || (key === 'to' ? 24 : 0)) : 0
  }
  const setHour = (key: 'from' | 'to', hour: number): void => {
    const w = minutes.value?.window
    if (w) w[key] = joinTime(hour, 0)
  }
  return { windowOn, hourOf, setHour }
}

function monthlyFields(monthly: Ref<Of<'monthly'> | null>) {
  const monthlyMode = computed<MonthlyMode>({
    get: () => (!monthly.value ? 'day' : 'lastDay' in monthly.value.on ? 'lastDay' : 'nth' in monthly.value.on ? 'nth' : 'day'),
    set: (mode) => {
      if (!monthly.value) return
      monthly.value.on = mode === 'day' ? { day: 1 } : mode === 'lastDay' ? { lastDay: true } : { nth: 1, weekday: 'MO' }
    },
  })
  const onDay = computed(() => (monthly.value && 'day' in monthly.value.on ? monthly.value.on : null))
  const onNth = computed(() => (monthly.value && 'nth' in monthly.value.on ? monthly.value.on : null))
  return { monthlyMode, onDay, onNth }
}

export function useScheduleFields(rule: Ref<PickerRule | null>) {
  const kinds = narrow(rule)
  const { minutes, weekly, monthly } = kinds
  return {
    ...kinds,
    ...windowFields(minutes),
    ...monthlyFields(monthly),
    onMinuteDay: (day: Weekday) => { if (minutes.value) minutes.value.days = toggleDay(minutes.value.days, day, false) },
    onWeekDay: (day: Weekday) => { if (weekly.value) weekly.value.days = toggleDay(weekly.value.days, day, true) },
  }
}
