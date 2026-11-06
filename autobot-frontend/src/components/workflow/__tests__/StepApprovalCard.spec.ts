// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// StepApprovalCard (#17677): the shared ApprovalEnvelope filled with a waiting step.

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import StepApprovalCard from '../StepApprovalCard.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const STEP = {
  step_id: 's1',
  command: 'systemctl restart nginx',
  description: 'Restart nginx',
  status: 'waiting_approval',
  requires_confirmation: true,
  risk_level: 'high',
  risk_tier: 'high',
  estimated_duration: 5,
  started_at: null,
  completed_at: null,
} as never

function mountCard(approve = vi.fn().mockResolvedValue(true), skip = vi.fn().mockResolvedValue(true)) {
  const wrapper = mount(StepApprovalCard, {
    props: { step: STEP, workflowId: 'wf-1', approve, skip },
    global: { plugins: [i18n] },
  })
  return { wrapper, approve, skip }
}

const button = (w: ReturnType<typeof mountCard>['wrapper'], label: string) =>
  w.findAll('button').find((b) => b.text() === label)!

describe('StepApprovalCard', () => {
  it('shows the step, its risk and the approve / skip pair', () => {
    const { wrapper } = mountCard()
    expect(wrapper.text()).toContain('Step waiting for your approval')
    expect(wrapper.text()).toContain('Restart nginx')
    expect(wrapper.text()).toContain('systemctl restart nginx')
    expect(wrapper.text()).toContain('High')
    expect(button(wrapper, 'Approve')).toBeTruthy()
    expect(button(wrapper, 'Skip step')).toBeTruthy()
  })

  it('approves and skips by workflow and step id', async () => {
    const { wrapper, approve, skip } = mountCard()
    await button(wrapper, 'Approve').trigger('click')
    expect(approve).toHaveBeenCalledWith('wf-1', 's1')
    await button(wrapper, 'Skip step').trigger('click')
    expect(skip).toHaveBeenCalledWith('wf-1', 's1')
  })

  it('blocks a second click while the first decision is in flight', async () => {
    let release!: () => void
    const approve = vi.fn(() => new Promise<void>((r) => { release = r }))
    const { wrapper } = mountCard(approve)
    await button(wrapper, 'Approve').trigger('click')
    await button(wrapper, 'Approve').trigger('click')
    await button(wrapper, 'Skip step').trigger('click')
    expect(approve).toHaveBeenCalledTimes(1)
    expect(button(wrapper, 'Approve').attributes('disabled')).toBeDefined()
    release()
    await new Promise((r) => setTimeout(r, 0))
    expect(button(wrapper, 'Approve').attributes('disabled')).toBeUndefined()
  })

  it('is a labelled region with a separate sr-only polite announcement and does not take focus', () => {
    const { wrapper } = mountCard()
    const region = wrapper.find('[role="region"]')
    expect(region.attributes('aria-label')).toBe('Step waiting for your approval')
    expect(region.attributes('aria-live')).toBeUndefined()
    const note = wrapper.find('[data-testid="step-approval-announcement"]')
    expect(note.classes()).toContain('sr-only')
    expect(note.attributes('aria-live')).toBe('polite')
    expect(note.text()).toBe('Step waiting for your approval')
    expect(note.find('button').exists()).toBe(false)
    expect(wrapper.find('[autofocus]').exists()).toBe(false)
  })

  it('a rejecting answer is contained and the buttons come back for a retry', async () => {
    const approve = vi.fn().mockRejectedValue(new Error('network'))
    const { wrapper } = mountCard(approve)
    await button(wrapper, 'Approve').trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(button(wrapper, 'Approve').attributes('disabled')).toBeUndefined()
  })
})
