// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Component test for ApprovalRequestCard's risk-level colour class (#14955).
 *
 * `riskLevel` is populated from `message.metadata.risk_level`
 * (`MessageItem.vue:158`), which originates from
 * `models/command_execution.py::RiskLevel` — uppercase
 * `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`. This card's `getRiskClass` now shares
 * the canonical normalization in `@/utils/riskLevel` with
 * `useCommandApproval`'s copy (#14955 asked to reconcile the two
 * independently-maintained tables); this test is the round-trip guard so a
 * future edit to either side cannot silently diverge again.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import ApprovalRequestCard from '../ApprovalRequestCard.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      chat: {
        approval: {
          approvalRequired: 'Approval Required',
          command: 'Command',
          riskLevel: 'Risk Level',
          purpose: 'Purpose',
          reasons: 'Reasons'
        }
      }
    }
  }
})

function mountCard(riskLevel: string) {
  return mount(ApprovalRequestCard, {
    props: { requiresApproval: true, status: null, command: 'rm -rf /', riskLevel },
    global: { plugins: [i18n] }
  })
}

describe('ApprovalRequestCard risk-level class', () => {
  it('renders CRITICAL with the critical class, not the low-risk default', () => {
    const wrapper = mountCard('CRITICAL')
    const riskSpan = wrapper.find('.detail-value.risk-critical, .risk-critical')
    expect(riskSpan.exists()).toBe(true)
    expect(wrapper.html()).not.toContain('risk-low')
  })

  it('renders MEDIUM with the medium class', () => {
    const wrapper = mountCard('MEDIUM')
    expect(wrapper.find('.risk-medium').exists()).toBe(true)
  })
})
