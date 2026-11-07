// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The tracing time-range buttons are `performance.tracingView.range.*` keys
 * resolved with t() (#20765). The control locale uses strings that appear nowhere
 * in the view, so a label left as a literal cannot pass.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import TracingView from './TracingView.vue'

vi.mock('@/composables/usePerformanceMonitoring', () => ({
  usePerformanceMonitoring: () => ({
    traces: ref([]),
    traceTotal: ref(0),
    loading: ref(false),
    error: ref(null),
    fetchTraces: vi.fn().mockResolvedValue(undefined),
    fetchTraceDetail: vi.fn().mockResolvedValue(null),
  }),
}))

const CONTROL = {
  performance: {
    tracingView: { range: { '1h': 'ctl-hour', '6h': 'ctl-six', '24h': 'ctl-day', '7d': 'ctl-week' } },
  },
}

function rangeLabels(messages: Record<string, object>): string[] {
  const i18n = createI18n({ legacy: false, locale: 'xx', fallbackLocale: 'xx', messages: { xx: messages } })
  const wrapper = mount(TracingView, { global: { plugins: [i18n] } })
  // The first button group in the filter bar is the time range selector.
  return wrapper.get('.overflow-hidden').findAll('button').map((b) => b.text())
}

describe('TracingView time-range labels (#20765)', () => {
  it('renders the control-locale strings, so the labels are not literals', () => {
    expect(rangeLabels(CONTROL)).toEqual(['ctl-hour', 'ctl-six', 'ctl-day', 'ctl-week'])
  })

  it('renders the English locale values', () => {
    expect(rangeLabels(en)).toEqual(['1h', '6h', '24h', '7d'])
  })
})
