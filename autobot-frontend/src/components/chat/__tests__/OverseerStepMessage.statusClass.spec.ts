// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Every OverseerStepStatus the backend emits must style the step and carry a
 * translated label (#19623). `waiting_explanation` previously had neither.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import en from '@/i18n/locales/en.json'
import OverseerStepMessage from '../OverseerStepMessage.vue'
import type { OverseerStepStatus } from '@/types/_generated/workflow'

vi.mock('@/components/ui/Icon.vue', () => ({
  default: { name: 'Icon', template: '<i class="icon-stub" />', props: ['name'] },
}))

const STATUSES: OverseerStepStatus[] = [
  'pending', 'running', 'streaming', 'waiting_explanation',
  'explaining', 'completed', 'failed',
]

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })

function mountStep(status: OverseerStepStatus) {
  return mount(OverseerStepMessage, {
    props: { step: { step_number: 1, total_steps: 2, description: 'd', status } },
    global: { plugins: [i18n] },
  })
}

describe('OverseerStepMessage status styling (#19623)', () => {
  it.each(STATUSES)('%s sets its status class on the step root', (status) => {
    expect(mountStep(status).find('.overseer-step').classes()).toContain(status)
  })

  it('waiting_explanation shows its translated label, not the raw key', () => {
    const text = mountStep('waiting_explanation').find('.step-status').text()
    expect(text).toBe('Waiting for explanation')
  })

  it('waiting_explanation has a .step-status colour rule', () => {
    const src = readFileSync(resolve(__dirname, '../OverseerStepMessage.vue'), 'utf-8')
    expect(src).toMatch(/\.step-status\.waiting_explanation\s*\{/)
  })
})
