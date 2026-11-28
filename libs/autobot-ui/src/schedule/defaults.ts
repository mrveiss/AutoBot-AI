// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Starting PickerRule for each repeat — what the picker shows after the user
// switches "Repeats", keeping the chosen time where the new repeat has one.

import { DEFAULT_TIME, type LocalTime, type PickerRule, type RepeatKind } from './types'
import { zoneDate } from './zone'

export function defaultRule(
  repeat: RepeatKind, time: LocalTime = DEFAULT_TIME, zone = 'UTC', now: number = Date.now(),
): PickerRule {
  switch (repeat) {
    case 'minutes':
      return { repeat, every: 15 }
    case 'hourly':
      return { repeat, minute: 0 }
    case 'daily':
      return { repeat, time, weekdaysOnly: true }
    case 'weekly':
      return { repeat, time, days: ['MO'] }
    case 'monthly':
      return { repeat, time, on: { day: 1 } }
    case 'once':
      return { repeat, date: zoneDate(now, zone, 1), time }
  }
}

/** The time of a rule, if its repeat has one. */
export function ruleTime(rule: PickerRule | null): LocalTime | undefined {
  return rule && 'time' in rule ? rule.time : undefined
}
