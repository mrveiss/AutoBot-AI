// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The performance tab labels are `performanceView.tabs.*` keys resolved with t()
 * (#19885); TabbedRouteLayout renders `tab.label` verbatim, so the view must pass
 * translated text.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import PerformanceView from './PerformanceView.vue'

vi.mock('@/composables/usePerformanceMonitoring', () => ({
  usePerformanceMonitoring: () => ({
    overview: ref(null),
    loading: ref(false),
    poller: ref(null),
  }),
}))
vi.mock('@/composables/monitoringPollContext', () => ({ providePerformanceMonitoring: () => undefined }))

const Layout = {
  props: ['tabs'],
  template: '<div><span v-for="tab in tabs" :key="tab.id" class="tab">{{ tab.label }}</span></div>',
}

function labels(locale: 'en' | 'de'): string[] {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', messages: { en, de } })
  const wrapper = mount(PerformanceView, {
    global: { plugins: [i18n], stubs: { TabbedRouteLayout: Layout, PollingPausedAlert: true } },
  })
  return wrapper.findAll('.tab').map((tab) => tab.text())
}

describe('PerformanceView tab labels (#19885)', () => {
  it('renders the English labels from the keys', () => {
    expect(labels('en')).toEqual(['Overview', 'Traces', 'SLOs', 'Alert Rules'])
  })

  it('renders the German labels, not the English literals', () => {
    expect(labels('de')).toEqual(['Übersicht', 'Traces', 'SLOs', 'Alarmregeln'])
  })
})
