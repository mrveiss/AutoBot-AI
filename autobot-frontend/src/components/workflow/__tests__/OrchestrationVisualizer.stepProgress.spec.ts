// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The visualizer's progress detail comes from the shared helper (#21106).

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import OrchestrationVisualizer from '../OrchestrationVisualizer.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const wf = (over: Record<string, unknown>) => ({
  workflow_id: 'wf-1', name: 'n', description: '', session_id: 's', current_step: 2, total_steps: 5,
  is_paused: false, is_cancelled: false, automation_mode: 'semi_automatic', user_interventions: [],
  started_at: '2026-11-08T10:00:00Z', steps: [], ...over,
})

function progress(w: unknown): string {
  const m = mount(OrchestrationVisualizer, {
    props: { status: null, strategies: {}, currentWorkflow: w as never, loading: false },
    global: { plugins: [i18n] },
  })
  const row = m.findAll('.detail-item').find((d) => d.find('.label').text() === en.workflow.orchestration.progress)
  return row!.find('.value').text()
}

describe('OrchestrationVisualizer step progress (#21106)', () => {
  it('shows N / N for a successfully completed run', () => {
    expect(progress(wf({ current_step: 6, completed_at: '2026-11-08T10:05:00Z' }))).toBe('5 / 5')
  })

  it('shows the step reached for a cancelled run, never 5 / 5', () => {
    expect(progress(wf({ is_cancelled: true, completed_at: '2026-11-08T10:05:00Z' }))).toBe('2 / 5')
  })
})
