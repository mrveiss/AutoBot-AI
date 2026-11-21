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
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/locales/en.json'
import TracingView from './TracingView.vue'

const fetchTraces = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))

vi.mock('@/composables/usePerformanceMonitoring', () => ({
  usePerformanceMonitoring: () => ({
    traces: ref([]),
    traceTotal: ref(0),
    loading: ref(false),
    error: ref(null),
    fetchTraces,
    fetchTraceDetail: vi.fn().mockResolvedValue(null),
  }),
}))

const CONTROL = {
  performance: {
    tracingView: { range: { '1h': 'ctl-hour', '6h': 'ctl-six', '24h': 'ctl-day', '7d': 'ctl-week' } },
  },
}

function mountView(messages: Record<string, object>) {
  const i18n = createI18n({ legacy: false, locale: 'xx', fallbackLocale: 'xx', messages: { xx: messages } })
  return mount(TracingView, { global: { plugins: [i18n] } })
}

function rangeLabels(messages: Record<string, object>): string[] {
  // The first button group in the filter bar is the time range selector.
  return mountView(messages).get('.overflow-hidden').findAll('button').map((b) => b.text())
}

describe('TracingView time-range labels (#20765)', () => {
  it('renders the control-locale strings, so the labels are not literals', () => {
    expect(rangeLabels(CONTROL)).toEqual(['ctl-hour', 'ctl-six', 'ctl-day', 'ctl-week'])
  })

  it('renders the English locale values', () => {
    expect(rangeLabels(en)).toEqual(['1h', '6h', '24h', '7d'])
  })

  it('sends the hours of the clicked range, so swapped values are caught', async () => {
    const wrapper = mountView(CONTROL)
    const sent: Record<string, number> = {}
    for (const button of wrapper.get('.overflow-hidden').findAll('button')) {
      fetchTraces.mockClear()
      await button.trigger('click')
      await flushPromises()
      sent[button.text()] = fetchTraces.mock.calls[fetchTraces.mock.calls.length - 1]?.[0]?.hours
    }
    expect(sent).toEqual({ 'ctl-hour': 1, 'ctl-six': 6, 'ctl-day': 24, 'ctl-week': 168 })
  })
})
