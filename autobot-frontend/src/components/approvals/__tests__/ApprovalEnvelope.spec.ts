// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// ApprovalEnvelope (#13421): the shared frame for every approval surface.

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import ApprovalEnvelope from '../ApprovalEnvelope.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

function mountEnvelope(props: Record<string, unknown> = {}) {
  return mount(ApprovalEnvelope, {
    props: { title: 'Run the plan', ...props },
    slots: { default: '<p class="detail">the bespoke detail</p>' },
    global: { plugins: [i18n] },
  })
}

describe('ApprovalEnvelope', () => {
  it('renders the title, the bespoke slot and the default verbs', () => {
    const wrapper = mountEnvelope()
    expect(wrapper.text()).toContain('Run the plan')
    expect(wrapper.find('.detail').exists()).toBe(true)
    expect(wrapper.findAll('button').map((b) => b.text())).toEqual(['Approve', 'Reject'])
  })

  it('shows the risk tier as a translated label, never colour alone', () => {
    const wrapper = mountEnvelope({ risk: 'critical' })
    expect(wrapper.text()).toContain('Critical')
  })

  it('shows no risk badge when the record carries no tier', () => {
    const wrapper = mountEnvelope()
    expect(wrapper.text()).not.toMatch(/Low|Medium|High|Critical/)
  })

  it("uses the surface's own action labels when given", () => {
    const wrapper = mountEnvelope({ approveLabel: 'Approve and run', rejectLabel: 'Decline' })
    expect(wrapper.findAll('button').map((b) => b.text())).toEqual(['Approve and run', 'Decline'])
  })

  it('emits approve and reject', async () => {
    const wrapper = mountEnvelope()
    const [approve, reject] = wrapper.findAll('button')
    await approve.trigger('click')
    await reject.trigger('click')
    expect(wrapper.emitted('approve')).toHaveLength(1)
    expect(wrapper.emitted('reject')).toHaveLength(1)
  })

  it('disables both decisions while one is in flight', async () => {
    const wrapper = mountEnvelope({ deciding: true })
    const [approve, reject] = wrapper.findAll('button')
    expect(approve.attributes('disabled')).toBeDefined()
    expect(reject.attributes('disabled')).toBeDefined()
    await approve.trigger('click')
    expect(wrapper.emitted('approve')).toBeUndefined()
  })
})
