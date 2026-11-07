// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19929: the run duration carries the active locale's unit labels, not fixed English suffixes.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import WorkflowHistory from '../WorkflowHistory.vue'
import en from '@/i18n/locales/en.json'
import de from '@/i18n/locales/de.json'
import ur from '@/i18n/locales/ur.json'

const RUN = {
  workflow_id: 'w1',
  name: 'Nightly',
  description: 'd',
  steps: [],
  total_steps: 0,
  created_at: '2026-01-01T00:00:00Z',
  started_at: '2026-01-01T00:00:00Z',
  completed_at: '2026-01-01T00:01:15.900Z',
  is_cancelled: false,
}

function pageText(locale: string): string {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, de, ur } })
  const wrapper = mount(WorkflowHistory, {
    props: { workflows: [RUN] as never },
    global: { plugins: [i18n], stubs: { Icon: true } },
  })
  return wrapper.text()
}

describe('WorkflowHistory duration labels (#19929)', () => {
  it('shows the English suffixes unchanged in the English locale', () => {
    expect(pageText('en')).toContain('1m 15s')
  })
  it('shows the German minute label from the locale file', () => {
    expect(pageText('de')).toContain('1min 15s')
  })
  it('shows the Urdu labels from the locale file', () => {
    expect(pageText('ur')).toContain('1منٹ 15سیکنڈ')
  })
})
