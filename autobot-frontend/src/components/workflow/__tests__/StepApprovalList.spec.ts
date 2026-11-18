// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// StepApprovalList (#21033): the cards sit in a bounded scroll region in every parent state.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import StepApprovalList from '../StepApprovalList.vue'

const Card = defineComponent({ props: ['step'], setup: (p) => () => h('div', { 'data-testid': 'card' }, p.step.step_id) })
const STEPS = [{ step_id: 's1' }, { step_id: 's2' }] as never[]

function mountIn(state: 'loading' | 'error' | 'content') {
  const Parent = defineComponent({
    setup: () => () =>
      h('section', [
        h(StepApprovalList, { steps: STEPS, workflowId: 'wf-1', approve: async () => true, skip: async () => true }),
        h('div', { 'data-testid': `state-${state}` }),
      ]),
  })
  return mount(Parent, { global: { stubs: { StepApprovalCard: Card } } })
}

describe('StepApprovalList', () => {
  it.each(['loading', 'error', 'content'] as const)('renders bounded cards in the %s state', (state) => {
    const w = mountIn(state)
    const list = w.get('[data-testid="step-approval-list"]')
    expect(list.classes()).toEqual(expect.arrayContaining(['max-h-96', 'overflow-y-auto']))
    expect(list.findAll('[data-testid="card"]')).toHaveLength(2)
  })

  it('renders nothing for an empty steps list', () => {
    const w = mount(StepApprovalList, { props: { steps: [], workflowId: 'w', approve: async () => true, skip: async () => true } as never })
    expect(w.find('[data-testid="step-approval-list"]').exists()).toBe(false)
  })
})
