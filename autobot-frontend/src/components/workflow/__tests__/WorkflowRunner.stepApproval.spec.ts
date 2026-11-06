// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// The runner shows a waiting step as the shared StepApprovalCard, not its own buttons (#17677).

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import StepApprovalCard from '@/components/workflow/StepApprovalCard.vue'
import WorkflowRunner from '../WorkflowRunner.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const WF = {
  workflow_id: 'wf-1', name: 'n', description: '', session_id: 's', current_step: 0, total_steps: 1,
  is_paused: false, is_cancelled: false, automation_mode: 'semi_automatic', user_interventions: [],
  steps: [{
    step_id: 's1', description: 'Restart nginx', command: 'systemctl restart nginx',
    status: 'waiting_approval', requires_confirmation: true, risk_level: 'high', risk_tier: 'high',
    estimated_duration: 5, started_at: null, completed_at: null,
  }],
} as never

describe('WorkflowRunner waiting step', () => {
  it('renders the approval card and answers through the passed handlers', async () => {
    const approveStep = vi.fn().mockResolvedValue(true)
    const wrapper = mount(WorkflowRunner, {
      props: { workflows: [WF], currentWorkflow: WF, loading: false, approveStep, skipStep: vi.fn() },
      global: { plugins: [i18n], stubs: { WorkflowNotificationConfig: true } },
    })
    expect(wrapper.findComponent(StepApprovalCard).exists()).toBe(true)
    expect(wrapper.find('.step-actions').exists()).toBe(false)
    await wrapper.findComponent(StepApprovalCard).findAll('button').find((b) => b.text() === 'Approve')!.trigger('click')
    expect(approveStep).toHaveBeenCalledWith('wf-1', 's1')
  })
})
