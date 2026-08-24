// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Tests for useCommandApproval#getRiskClass (#14955).
 *
 * `ChatMessages.vue:327` renders
 * `<span :class="getRiskClass((message.metadata as any).risk_level)">` where
 * `message.metadata.risk_level` originates from
 * `models/command_execution.py::RiskLevel` — uppercase
 * `LOW`/`MEDIUM`/`HIGH`/`CRITICAL` (see `CommandExecution.to_dict()` and
 * `api/agent_terminal.py`'s `risk_level` field). Before this fix, the
 * lookup table was keyed on `MODERATE`/`DANGEROUS`, vocabulary from a
 * *different* enum (`CommandRisk`) that never reaches this call site, so a
 * real `CRITICAL` command fell through to the neutral/unclassified class.
 *
 * This test mounts the exact binding expression used by ChatMessages.vue
 * and asserts on the rendered DOM class, not just the helper's return
 * value in isolation.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useCommandApproval } from '@/composables/useCommandApproval'

const UNCLASSIFIED_CLASS = 'text-gray-600'

/** Mirrors ChatMessages.vue:327's `:class="getRiskClass(risk_level)"` binding. */
function mountRiskSpan(riskLevel: string) {
  const Test = defineComponent({
    setup() {
      const { getRiskClass } = useCommandApproval()
      return () => h('span', { class: getRiskClass(riskLevel) }, riskLevel)
    }
  })
  return mount(Test)
}

describe('useCommandApproval getRiskClass — rendered output', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders a CRITICAL command with a distinct, non-default class', () => {
    const wrapper = mountRiskSpan('CRITICAL')
    expect(wrapper.classes()).not.toContain(UNCLASSIFIED_CLASS)
    expect(wrapper.classes()).toContain('text-red-600')
  })

  it('renders a MEDIUM command with a distinct, non-default class', () => {
    const wrapper = mountRiskSpan('MEDIUM')
    expect(wrapper.classes()).not.toContain(UNCLASSIFIED_CLASS)
    expect(wrapper.classes()).toContain('text-yellow-600')
  })

  it('renders LOW and HIGH commands with distinct classes', () => {
    expect(mountRiskSpan('LOW').classes()).toContain('text-green-600')
    expect(mountRiskSpan('HIGH').classes()).toContain('text-orange-600')
  })

  it('falls back to the unclassified class only for a value no producer emits', () => {
    const wrapper = mountRiskSpan('SOMETHING_UNKNOWN')
    expect(wrapper.classes()).toContain(UNCLASSIFIED_CLASS)
  })
})
