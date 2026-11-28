// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #13714: with no mailbox backend, the screen says inbound mail is not available
 * and offers nothing that looks usable -- no rows, no compose, no buttons.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import MailboxView from '../MailboxView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const M = en.llc.mailbox

describe('MailboxView', () => {
  const wrapper = mount(MailboxView, { global: { plugins: [i18n] } })

  it('states plainly that inbound mail is not available yet', () => {
    const empty = wrapper.get('[data-testid="mailbox-unavailable"]')
    expect(empty.text()).toContain(M.unavailableTitle)
    expect(empty.text()).toContain(M.unavailableBody)
  })

  it('shows the screen title', () => {
    expect(wrapper.get('h1').text()).toBe(M.title)
  })

  it('has no controls and no list rows to mistake for working mail', () => {
    expect(wrapper.findAll('button, input, textarea, select, a, li, tr')).toHaveLength(0)
  })
})
