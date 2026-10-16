// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// SchedulePicker behaviour (#18432): what it emits, what it shows, how it
// degrades without a server, and its accessible structure.

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import SchedulePicker from '../SchedulePicker.vue'
import type { PreviewResult, ScheduleSpec } from '../../schedule'

const translate = (key: string, params?: Record<string, unknown>) =>
  params && Object.keys(params).length ? `${key}(${JSON.stringify(params)})` : key

function make(modelValue: ScheduleSpec | null, extra: Record<string, unknown> = {}) {
  return mount(SchedulePicker, { props: { modelValue, translate, debounceMs: 0, defaultTimezone: 'UTC', ...extra } })
}
const last = (w: ReturnType<typeof make>): ScheduleSpec => {
  const ev = w.emitted('update:modelValue')!
  return ev[ev.length - 1][0] as ScheduleSpec
}
const cron = (c: string, timezone = 'UTC'): ScheduleSpec => ({ kind: 'cron', timezone, cron: c })

describe('SchedulePicker', () => {
  it('with no model emits a default weekday schedule on mount', () => {
    const w = make(null)
    expect(last(w)).toEqual(cron('0 9 * * 1-5'))
  })

  it('shows an existing cron as a derived summary, not as cron', () => {
    const w = make(cron('0 9 * * 1-5'))
    expect(w.find('.aui-sched__summary').text()).toContain('schedule.summary.withZone')
    expect(w.find('.aui-sched__summary').text()).toContain('schedule.summary.dailyWeekdays')
    expect(w.find('.aui-sched__summary').text()).not.toContain('* *')
    expect(w.emitted('update:modelValue')).toBeUndefined() // reading never rewrites stored data
  })

  it('weekly: day chips are toggle buttons with aria-pressed and emit cron', async () => {
    const w = make(cron('0 9 * * 1'))
    const chips = w.findAll('button.aui-chip')
    expect(chips).toHaveLength(7)
    expect(chips[0].attributes('aria-pressed')).toBe('true')
    expect(chips[2].attributes('aria-pressed')).toBe('false')
    await chips[2].trigger('click')
    expect(last(w)).toEqual(cron('0 9 * * 1,3'))
    await chips[0].trigger('click')
    await chips[2].trigger('click') // last chip cannot be switched off
    expect(chips[2].attributes('aria-pressed')).toBe('true')
    expect(last(w)).toEqual(cron('0 9 * * 3'))
  })

  it('repeats is a radiogroup; choosing monthly day 31 emits a calendar rule', async () => {
    const preview = vi.fn().mockResolvedValue({ valid: true, next_runs: ['2030-01-01T09:00:00Z'] })
    const w = make(cron('0 9 * * *'), { preview })
    await flushPromises()
    const group = w.find('[role="radiogroup"]')
    expect(group.attributes('aria-labelledby')).toBeTruthy()
    expect(w.findAll('input[type="radio"]').length).toBeGreaterThanOrEqual(6)
    await w.findAll('input[type="radio"]')[4].setValue(true) // monthly
    expect(last(w)).toEqual(cron('0 9 1 * *'))
    const day = w.findAll('select').find((s) => s.findAll('option').length === 31)!
    await day.setValue(31)
    expect(last(w)).toEqual({ kind: 'calendar', timezone: 'UTC', rrule: 'FREQ=MONTHLY;BYMONTHDAY=28,29,30,31;BYSETPOS=-1;BYHOUR=9;BYMINUTE=0' })
    expect(w.text()).toContain('schedule.shortMonths')
  })

  it('a spec it cannot show is "Custom schedule" until a repeat is chosen', async () => {
    const w = make(cron('0 9,17 * * *'))
    expect(w.text()).toContain('schedule.summary.custom')
    await w.findAll('input[type="radio"]')[2].setValue(true)
    expect(last(w)).toEqual(cron('0 9 * * 1-5'))
  })

  it('changing the zone re-emits the same rule in the new zone', async () => {
    const w = make(cron('0 9 * * *'))
    await w.find('select[id$="-zone"]').setValue('Europe/Helsinki')
    expect(last(w)).toEqual(cron('0 9 * * *', 'Europe/Helsinki'))
  })

  it('has labelled fieldset/legend, labelled selects, and a live summary', () => {
    const w = make(cron('0 9 * * *'))
    expect(w.find('fieldset > legend').text()).toBe('schedule.title')
    expect(w.find('.aui-sched__summary').attributes('aria-live')).toBe('polite')
    for (const select of w.findAll('select')) {
      expect(w.find(`label[for="${select.attributes('id')}"]`).exists()).toBe(true)
    }
  })

  it('syncs an external model change without echoing an emit', async () => {
    const w = make(cron('0 9 * * *'))
    await w.setProps({ modelValue: cron('30 6 1 * *') })
    await flushPromises()
    expect(w.text()).toContain('schedule.summary.monthlyDay')
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })
})

describe('SchedulePicker cron-only gate', () => {
  const okPreview = () => vi.fn().mockResolvedValue({ valid: true, next_runs: ['2030-01-01T09:00:00Z'] })
  const radio = (w: ReturnType<typeof make>, label: string) =>
    w.findAll('label.aui-seg__item').find((l) => l.text() === label)!.find('input')

  async function toMonthly(w: ReturnType<typeof make>) {
    await radio(w, 'schedule.repeat.monthly').setValue(true)
  }

  it.each([
    ['no preview function', undefined],
    ['preview resolves null (404)', () => vi.fn().mockResolvedValue(null)],
    ['preview throws', () => vi.fn().mockRejectedValue(new Error('x'))],
  ])('%s: only cron-kind rules are offered, with a note', async (_n, mk) => {
    const w = make(cron('0 9 * * *'), { preview: mk?.() })
    await flushPromises()
    expect(w.text()).toContain('schedule.gatedNote')
    expect(radio(w, 'schedule.repeat.once').attributes('disabled')).toBeDefined()
    await toMonthly(w)
    expect(radio(w, 'schedule.monthly.lastDay').attributes('disabled')).toBeDefined()
    expect(radio(w, 'schedule.monthly.nth').attributes('disabled')).toBeDefined()
    expect(radio(w, 'schedule.monthly.day').attributes('disabled')).toBeUndefined()
    const options = w.findAll('select').find((s) => s.findAll('option').length === 31)!.findAll('option')
    expect(options[27].attributes('disabled')).toBeUndefined() // 28
    expect(options[28].attributes('disabled')).toBeDefined() // 29
    expect(options[30].attributes('disabled')).toBeDefined() // 31
    for (const e of w.emitted('update:modelValue') ?? []) expect((e[0] as ScheduleSpec).kind).toBe('cron')
    expect(w.emitted('update:previewAvailable')!.at(-1)).toEqual([false])
  })

  it('preview available: every kind is enabled and no note is shown', async () => {
    const w = make(cron('0 9 * * *'), { preview: okPreview() })
    await flushPromises()
    expect(w.text()).not.toContain('schedule.gatedNote')
    expect(radio(w, 'schedule.repeat.once').attributes('disabled')).toBeUndefined()
    await toMonthly(w)
    expect(radio(w, 'schedule.monthly.lastDay').attributes('disabled')).toBeUndefined()
    expect(radio(w, 'schedule.monthly.nth').attributes('disabled')).toBeUndefined()
    expect(w.emitted('update:previewAvailable')!.at(-1)).toEqual([true])
  })

  it('a stored non-cron spec stays selectable while gated (never forcibly rewritten)', async () => {
    const w = make({ kind: 'calendar', timezone: 'UTC', rrule: 'FREQ=MONTHLY;BYMONTHDAY=-1;BYHOUR=9;BYMINUTE=0' })
    await flushPromises()
    expect(radio(w, 'schedule.monthly.lastDay').attributes('disabled')).toBeUndefined()
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })
})

describe('SchedulePicker preview', () => {
  const ok = (runs: string[]): PreviewResult => ({ valid: true, next_runs: runs, kind: 'cron' })

  it('shows the advisory next 3 runs when no server preview is supplied', () => {
    const w = make(cron('0 9 * * *'))
    expect(w.findAll('.aui-sched__list li')).toHaveLength(3)
    expect(w.text()).toContain('schedule.previewApprox')
  })

  it('replaces the advisory runs with the server answer', async () => {
    const preview = vi.fn().mockResolvedValue(ok(['2030-01-01T09:00:00Z']))
    const w = make(cron('0 9 * * *'), { preview })
    await flushPromises()
    expect(preview).toHaveBeenCalledWith(cron('0 9 * * *'), 3)
    expect(w.findAll('.aui-sched__list li')).toHaveLength(1)
    expect(w.text()).not.toContain('schedule.previewApprox')
  })

  it('keeps the advisory runs when the endpoint is unavailable (null or throws)', async () => {
    for (const preview of [vi.fn().mockResolvedValue(null), vi.fn().mockRejectedValue(new Error('404'))]) {
      const w = make(cron('0 9 * * *'), { preview })
      await flushPromises()
      expect(w.findAll('.aui-sched__list li')).toHaveLength(3)
      expect(w.emitted('update:valid')!.every((e) => e[0] === true)).toBe(true)
    }
  })

  it('renders a server error by code with its params and reports invalid', async () => {
    const preview = vi.fn().mockResolvedValue({
      valid: false, error_code: 'schedule.once_in_past', error_params: { at: 'x' }, next_runs: [],
    })
    const w = make({ kind: 'once', timezone: 'UTC', at: '2020-01-01T00:00' }, { preview })
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toBe('schedule.once_in_past({"at":"x"})')
    const valid = w.emitted('update:valid')!
    expect(valid[valid.length - 1]).toEqual([false])
  })

  it('an unknown server code falls back to the generic message', async () => {
    const preview = vi.fn().mockResolvedValue({ valid: false, error_code: 'schedule.weird', next_runs: [] })
    const w = make(cron('0 9 * * *'), { preview })
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toBe('schedule.invalid_generic')
  })
})

describe('SchedulePicker expert mode', () => {
  async function openEditor(preview?: unknown) {
    const w = make(cron('0 9 * * 1-5'), { preview })
    await w.find('.aui-sched__adv .aui-link').trigger('click')
    await w.findAll('.aui-sched__adv .aui-link').at(-1)!.trigger('click') // Edit as cron
    return w
  }

  it('lists show no cron until Advanced is opened', () => {
    const w = make(cron('0 9 * * 1-5'))
    expect(w.html()).not.toContain('0 9 * * 1-5')
  })

  it('accepts a valid cron the picker can show and updates the picker', async () => {
    const w = await openEditor()
    await w.find('input[id$="-cron"]').setValue('30 6 * * *')
    await flushPromises()
    expect(last(w)).toEqual(cron('30 6 * * *'))
    expect(w.find('.aui-sched__summary').text()).toContain('schedule.summary.daily')
  })

  it('a cron the picker cannot show is accepted and shown as Custom schedule', async () => {
    const w = await openEditor()
    await w.find('input[id$="-cron"]').setValue('0 9,17 * * *')
    await flushPromises()
    expect(last(w)).toEqual(cron('0 9,17 * * *'))
    expect(w.text()).toContain('schedule.summary.custom')
  })

  it.each([
    ['5L', '0 9 * * 5L', 'schedule.cron_extension_unsupported({"token":"5L"})'],
    ['1#2', '0 9 * * 1#2', 'schedule.cron_extension_unsupported({"token":"1#2"})'],
    ['6 fields', '0 0 9 * * 1', 'schedule.invalid_cron'],
    ['garbage', 'hello world', 'schedule.invalid_cron'],
  ])('refuses %s and does not emit it', async (_n, text, message) => {
    const w = await openEditor()
    const before = w.emitted('update:modelValue')?.length ?? 0
    await w.find('input[id$="-cron"]').setValue(text)
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toBe(message)
    expect(w.emitted('update:modelValue')?.length ?? 0).toBe(before)
  })

  it('accepts text only when the server preview validates it', async () => {
    const preview = vi.fn(async (s: ScheduleSpec) =>
      s.kind === 'cron' && s.cron === '0 9 31 2 *'
        ? ({ valid: false, error_code: 'schedule.invalid_rrule', next_runs: [] } as PreviewResult)
        : ({ valid: true, next_runs: ['2030-01-01T09:00:00Z'] } as PreviewResult))
    const w = await openEditor(preview)
    const before = w.emitted('update:modelValue')?.length ?? 0
    await w.find('input[id$="-cron"]').setValue('0 9 31 2 *')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toBe('schedule.invalid_rrule')
    expect(w.emitted('update:modelValue')?.length ?? 0).toBe(before)
  })
})
