// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// The runner selects a listed workflow and starts a saved one (#21043).

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import WorkflowRunner from '../WorkflowRunner.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const base = {
  workflow_id: 'wf-1', name: 'n', description: '', session_id: 's', current_step: 0, total_steps: 1,
  is_paused: false, is_cancelled: false, automation_mode: 'semi_automatic', user_interventions: [],
  steps: [{ step_id: 's1', description: 'd', command: 'c', status: 'pending', risk_level: 'low' }],
}
const SAVED = base as never
const STARTED = { ...base, started_at: '2026-11-07T10:00:00Z' } as never

function mountRunner(current: unknown) {
  return mount(WorkflowRunner, {
    props: { workflows: [SAVED], currentWorkflow: current as never, loading: false, approveStep: async () => true, skipStep: async () => true },
    global: { plugins: [i18n], stubs: { WorkflowNotificationConfig: true } },
  })
}
const labels = (w: ReturnType<typeof mountRunner>) => w.findAll('button').map((b) => b.text())

describe('WorkflowRunner select and start (#21043)', () => {
  it('emits select-workflow with the id when a list item is clicked', async () => {
    const w = mountRunner(null)
    await w.find('.workflow-item').trigger('click')
    expect(w.emitted('select-workflow')).toEqual([['wf-1']])
  })

  it('shows Start for a not-started workflow and emits start-workflow', async () => {
    const w = mountRunner(SAVED)
    await w.findAll('button').find((b) => b.text() === 'Start')!.trigger('click')
    expect(w.emitted('start-workflow')).toEqual([['wf-1']])
  })

  it('hides Pause, Resume and Cancel before the start', () => {
    const l = labels(mountRunner(SAVED))
    for (const hidden of ['Pause', 'Resume', 'Cancel']) expect(l).not.toContain(hidden)
  })

  it('after the start shows Pause and Cancel and no Start', () => {
    const l = labels(mountRunner(STARTED))
    expect(l).toContain('Pause')
    expect(l).toContain('Cancel')
    expect(l).not.toContain('Start')
  })
})
