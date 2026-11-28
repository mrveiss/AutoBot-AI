// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * App-side glue for the shared schedule picker (#18432): the i18n translator,
 * the routine payload and the derived summary used by every list.
 *
 * Contract: ScheduleSpec / PickerRule live in @autobot/ui (libs/autobot-ui/
 * src/schedule). No server preview is wired: the backend route is the
 * backend half of #18432, and until it lands the picker shows its advisory
 * runs and stays cron-only (the kit's gate when no `preview` is passed).
 */
import { useI18n } from 'vue-i18n'
import {
  parseSpecToRule,
  summaryText,
  type ScheduleSpec,
  type ScheduleTranslate,
} from '@autobot/ui'

/**
 * Zones a routine can run in: the routine API stores only `cron_schedule` and the
 * scheduler evaluates it in UTC, so UTC until the zone is persisted end to end
 * (#18432's backend half).
 */
export const ROUTINE_ZONES = ['UTC'] as const

/**
 * Existing routines carry a bare cron string that the scheduler evaluates in
 * UTC today — it is read as {cron, UTC}, NOT the company zone, so nothing
 * silently shifts. A stored spec, once the backend provides one, wins.
 */
export function routineSpec(routine: { cron_schedule?: string | null; schedule_spec?: ScheduleSpec | null }): ScheduleSpec | null {
  if (routine.schedule_spec) return routine.schedule_spec
  return routine.cron_schedule ? { kind: 'cron', timezone: 'UTC', cron: routine.cron_schedule } : null
}

/**
 * Routine payload fragment: EXACTLY ONE of `cron_schedule` / `schedule_spec`.
 * A cron spec is today's payload; calendar and once go as `schedule_spec`
 * alone. Sending both is a 422 `schedule.conflicting_fields`.
 */
export function schedulePayload(spec: ScheduleSpec | null): Record<string, unknown> {
  if (!spec) return {}
  return spec.kind === 'cron' ? { cron_schedule: spec.cron } : { schedule_spec: spec }
}

/** Translator + locale bound to the app's i18n, in the shape the kit expects. */
export function useScheduleI18n() {
  const { t, locale } = useI18n()
  const translate: ScheduleTranslate = (key, params) => t(key, params ?? {})
  return { translate, locale }
}

/** `summarize(spec)` → "Every weekday at 09:00, UTC"; never cron. */
export function useScheduleSummary(companyTimezone?: () => string | undefined) {
  const { translate, locale } = useScheduleI18n()
  return (spec: ScheduleSpec | null): string => {
    if (!spec) return ''
    const zone = spec.timezone === companyTimezone?.() ? translate('schedule.zone.company') : spec.timezone
    return summaryText(parseSpecToRule(spec), zone, translate, locale.value)
  }
}
