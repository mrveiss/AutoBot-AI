// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The runner shows the backend's 1-based step as-is: never "3 / 2" (#21106).

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import WorkflowRunner from '../WorkflowRunner.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const step = (id: string, status: string) => ({ step_id: id, description: 'd', command: 'c', status, risk_level: 'low' })
const wf = (over: Record<string, unknown>) => ({
  workflow_id: 'wf-1', name: 'n', description: '', session_id: 's', current_step: 1, total_steps: 2,
  is_paused: false, is_cancelled: false, automation_mode: 'semi_automatic', user_interventions: [],
  steps: [step('a', 'pending'), step('b', 'pending')], ...over,
})

function mountRunner(w: unknown) {
  return mount(WorkflowRunner, {
    props: { workflows: [w] as never, currentWorkflow: w as never, loading: false, approveStep: async () => true, skipStep: async () => true },
    global: { plugins: [i18n], stubs: { WorkflowNotificationConfig: true } },
  })
}
const listProgress = (m: ReturnType<typeof mountRunner>) => m.find('.wf-progress').text()
const fill = (m: ReturnType<typeof mountRunner>) => m.find('.progress-bar-large .progress-fill').attributes('style')

describe('WorkflowRunner step progress (#21106)', () => {
  it('shows a not-started run as 0 / 2', () => {
    expect(listProgress(mountRunner(wf({})))).toBe('Step 0 / 2')
  })

  it('shows 1 / 2 then 2 / 2 while running', () => {
    const t = { started_at: '2026-11-08T10:00:00Z' }
    expect(listProgress(mountRunner(wf({ ...t, current_step: 1 })))).toBe('Step 1 / 2')
    expect(listProgress(mountRunner(wf({ ...t, current_step: 2 })))).toBe('Step 2 / 2')
  })

  it('shows 2 / 2 and a full bar at completion, never 3 / 2', () => {
    const m = mountRunner(wf({ started_at: 't', completed_at: 't', current_step: 3, steps: [step('a', 'completed'), step('b', 'completed')] }))
    expect(listProgress(m)).toBe('Step 2 / 2')
    expect(fill(m)).toContain('width: 100%')
    expect(m.find('.progress-stats .value').text()).toBe('2')
  })
})
