// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ApprovalCard from '../ApprovalCard.vue'

describe('ApprovalCard', () => {
  const defaultProps = {
    approval: {
      sessionId: 's1',
      experimentId: 'e1',
      metrics: {
        baseline_val_bpb: 5.0,
        result_val_bpb: 4.5,
        improvement_pct: 10.0,
      },
    },
  }

  it('renders approval details', () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps })
    expect(wrapper.text()).toContain('Approval Required')
    expect(wrapper.text()).toContain('5.0000')
    expect(wrapper.text()).toContain('4.5000')
    expect(wrapper.text()).toContain('10.00%')
  })

  it('emits approve event on button click', async () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps })
    await wrapper.find('button:first-of-type').trigger('click')
    expect(wrapper.emitted('approve')).toBeTruthy()
    expect(wrapper.emitted('approve')![0]).toEqual(['s1', 'e1'])
  })

  it('emits reject event on button click', async () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps })
    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('reject')).toBeTruthy()
  })
})
