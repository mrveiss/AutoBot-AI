// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #18432: every key the shared picker can ask for exists in ALL 11 locales, and
// every summary shape renders as prose (a missing key would render as its name).

import { describe, it, expect, beforeAll, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { compilePickerRule, WEEKDAYS, type PickerRule } from '@autobot/ui'

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ post: vi.fn().mockRejectedValue(new Error('HTTP 404')) }) }))

import SchedulePickerField from '../SchedulePickerField.vue'

const files = import.meta.glob('@/i18n/locales/*.json', { eager: true, import: 'default' }) as Record<string, Record<string, unknown>>
const locales = Object.fromEntries(Object.entries(files).map(([p, m]) => [p.split('/').pop()!.replace('.json', ''), m]))

const RULES: PickerRule[] = [
  { repeat: 'minutes', every: 15 },
  { repeat: 'minutes', every: 15, days: ['MO', 'WE'] },
  { repeat: 'minutes', every: 15, window: { from: '08:00', to: '18:00' }, days: [...WEEKDAYS].slice(0, 5) },
  { repeat: 'hourly', minute: 5 },
  { repeat: 'daily', time: '09:00', weekdaysOnly: true },
  { repeat: 'weekly', time: '09:00', days: ['MO', 'FR'] },
  { repeat: 'monthly', time: '09:00', on: { day: 31 } },
  { repeat: 'monthly', time: '09:00', on: { lastDay: true } },
  { repeat: 'monthly', time: '09:00', on: { nth: -1, weekday: 'FR' } },
  { repeat: 'monthly', time: '09:00', on: { nth: 3, weekday: 'TU' } },
  { repeat: 'once', date: '2030-01-02', time: '08:00' },
]

describe('SchedulePickerField i18n (#18432)', () => {
  beforeAll(async () => {
    const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: locales.en as never } })
    mount(SchedulePickerField, { props: { modelValue: null }, global: { plugins: [i18n] } })
    await flushPromises()
  })

  it('ships the schedule namespace in all 11 locales with identical keys', () => {
    expect(Object.keys(locales).sort()).toHaveLength(11)
    const flat = (o: unknown, p = ''): string[] =>
      typeof o === 'object' && o ? Object.entries(o).flatMap(([k, v]) => flat(v, p ? `${p}.${k}` : k)) : [p]
    const en = flat((locales.en as Record<string, unknown>).schedule).sort()
    expect(en.length).toBeGreaterThan(70)
    for (const [code, messages] of Object.entries(locales)) {
      expect(flat((messages as Record<string, unknown>).schedule).sort(), code).toEqual(en)
    }
  })

  // One mount per test: a locale's 11 rules in one test was ~5 s unloaded and
  // outran the 10 s timeout under pre-push load (#18254).
  const CASES = Object.keys(locales).flatMap((code) => RULES.map((rule) => [code, JSON.stringify(rule), rule] as const))
  it.each(CASES)('%s: %s summary and the picker chrome render as prose, not keys', async (code, label, rule) => {
    const i18n = createI18n({ legacy: false, locale: code, fallbackLocale: 'en', missingWarn: false, messages: locales as never })
    const wrapper = mount(SchedulePickerField, { props: { modelValue: compilePickerRule(rule, 'UTC') }, global: { plugins: [i18n] } })
    await flushPromises()
    expect(wrapper.find('.aui-sched__summary').text(), label).not.toMatch(/schedule\.|\{|\}/)
    expect(wrapper.text(), label).not.toMatch(/schedule\.[a-zA-Z_]+/)
    wrapper.unmount()
  })

  it.each(Object.keys(locales))('%s: server error codes render as prose', async (code) => {
    const i18n = createI18n({ legacy: false, locale: code, fallbackLocale: 'en', missingWarn: false, messages: locales as never })
    const wrapper = mount(SchedulePickerField, { props: { modelValue: { kind: 'once', timezone: 'UTC', at: '2020-01-01T00:00' } }, global: { plugins: [i18n] } })
    await flushPromises()
    await wrapper.find('.aui-sched__adv .aui-link').trigger('click')
    await wrapper.findAll('.aui-sched__adv .aui-link').at(-1)!.trigger('click')
    for (const [text, token] of [['0 9 * * 5L', '5L'], ['0 0 9 * * 1', '']]) {
      await wrapper.find('input[id$="-cron"]').setValue(text)
      await flushPromises()
      const msg = wrapper.find('[role="alert"]').text()
      expect(msg).not.toMatch(/schedule\./)
      if (token) expect(msg).toContain(token)
    }
  })
})
