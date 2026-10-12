// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #18432: app glue for the schedule picker.

import { describe, it, expect, vi } from 'vitest'

const post = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ post }) }))

import { routineSpec, schedulePayload, useSchedulePreviewCall } from '../useSchedule'

describe('routineSpec', () => {
  it('reads a bare cron string as UTC, never the company zone (no silent shift)', () => {
    expect(routineSpec({ cron_schedule: '0 9 * * 1-5' })).toEqual({ kind: 'cron', timezone: 'UTC', cron: '0 9 * * 1-5' })
  })
  it('prefers a stored spec', () => {
    const spec = { kind: 'calendar' as const, timezone: 'Europe/Helsinki', rrule: 'FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=9;BYMINUTE=0' }
    expect(routineSpec({ cron_schedule: '0 9 1 * *', schedule_spec: spec })).toBe(spec)
  })
  it('has no spec for a routine with no schedule', () => {
    expect(routineSpec({ cron_schedule: '' })).toBeNull()
  })
})

describe('useSchedulePreviewCall', () => {
  const spec = { kind: 'cron' as const, timezone: 'UTC', cron: '0 9 * * *' }
  it('posts {spec, count} to the preview endpoint and returns the body', async () => {
    post.mockResolvedValueOnce({ valid: true, next_runs: ['2030-01-01T09:00:00Z'] })
    expect(await useSchedulePreviewCall()(spec, 3)).toEqual({ valid: true, next_runs: ['2030-01-01T09:00:00Z'] })
    expect(post).toHaveBeenCalledWith('/api/schedules/preview', { spec, count: 3 })
  })
  it('resolves null (preview unavailable) when the endpoint 404s', async () => {
    post.mockRejectedValueOnce(new Error('HTTP 404: Not Found'))
    expect(await useSchedulePreviewCall()(spec, 3)).toBeNull()
  })
})

describe('schedulePayload', () => {
  it('sets exactly one of cron_schedule / schedule_spec', () => {
    expect(schedulePayload({ kind: 'cron', timezone: 'UTC', cron: '0 9 * * *' })).toEqual({ cron_schedule: '0 9 * * *' })
    const cal = { kind: 'calendar' as const, timezone: 'UTC', rrule: 'FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=9;BYMINUTE=0' }
    expect(schedulePayload(cal)).toEqual({ schedule_spec: cal })
    const once = { kind: 'once' as const, timezone: 'UTC', at: '2030-01-01T09:00' }
    expect(schedulePayload(once)).toEqual({ schedule_spec: once })
    expect(schedulePayload(null)).toEqual({})
  })
})
