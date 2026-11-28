// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ApprovalCard from '../ApprovalCard.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

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
    const wrapper = mount(ApprovalCard, { props: defaultProps, global: { plugins: [i18n] } })
    expect(wrapper.text()).toContain('Approval Required')
    expect(wrapper.text()).toContain('5.0000')
    expect(wrapper.text()).toContain('4.5000')
    expect(wrapper.text()).toContain('10.00%')
  })

  it('emits approve event on button click', async () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps, global: { plugins: [i18n] } })
    await wrapper.find('button:first-of-type').trigger('click')
    expect(wrapper.emitted('approve')).toBeTruthy()
    expect(wrapper.emitted('approve')![0]).toEqual(['s1', 'e1'])
  })

  it('emits reject event on button click', async () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps, global: { plugins: [i18n] } })
    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('reject')![0]).toEqual(['s1', 'e1'])
  })

  it('disables both decisions after one is sent', async () => {
    const wrapper = mount(ApprovalCard, { props: defaultProps, global: { plugins: [i18n] } })
    await wrapper.findAll('button')[0].trigger('click')
    wrapper.findAll('button').forEach((b) => expect(b.attributes('disabled')).toBeDefined())
  })
})
