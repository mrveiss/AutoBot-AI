// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Component test for ApprovalRequestCard's risk-level colour class (#14955).
 *
 * `riskLevel` is populated from `message.metadata.risk_level`
 * (`MessageItem.vue:158`), which is contracted to
 * `models/command_execution.py::RiskLevel` -- uppercase
 * `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`. This card's `getRiskClass` shares the
 * canonical normalization in `@/utils/riskLevel` with `useCommandApproval`'s
 * copy, so the two tables can't silently diverge again.
 *
 * Review of the first version of this fix found a second, more severe leak
 * of the SAME bug: `services/agent_terminal/service.py::
 * _queue_command_for_approval` was forwarding the raw, lowercase
 * `CommandRisk.value` (e.g. "dangerous", "forbidden") into the
 * pending-approval response instead of the converted `RiskLevel`, and this
 * card's old fallback ('risk-low', green/success) meant an unrecognized
 * value rendered as the safest-looking colour on the exact surface a user
 * is about to approve a destructive command from. That producer is now
 * fixed to always emit the canonical vocabulary -- but the tests below also
 * guard the frontend's own fallback so a future producer regression can
 * never again render an unclassified/raw-CommandRisk value as low-risk.
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

const DESTRUCTIVE_TEST_COMMAND = 'shutdown --now'

function mountCard(riskLevel: string) {
  return mount(ApprovalRequestCard, {
    props: { requiresApproval: true, status: null, command: DESTRUCTIVE_TEST_COMMAND, riskLevel },
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

  it('never renders a raw CommandRisk "dangerous" value as low-risk/green', () => {
    const wrapper = mountCard('dangerous')
    expect(wrapper.find('.risk-low').exists()).toBe(false)
    expect(wrapper.find('.risk-unknown').exists()).toBe(true)
  })

  it('never renders a raw CommandRisk "forbidden" value as low-risk/green', () => {
    const wrapper = mountCard('forbidden')
    expect(wrapper.find('.risk-low').exists()).toBe(false)
    expect(wrapper.find('.risk-unknown').exists()).toBe(true)
  })
})
