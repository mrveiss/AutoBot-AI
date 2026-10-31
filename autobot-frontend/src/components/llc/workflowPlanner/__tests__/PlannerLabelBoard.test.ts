// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19938: the label board groups sub-steps by label, offers a label for each unlabelled one, and
// holds the By Hand read-through behind an explicit acknowledgement.

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import PlannerLabelBoard from '../PlannerLabelBoard.vue'
import { breakdownWith, isNotFoundError, plannerEntryPoint, withStep } from '@/composables/llc/workflowPlanTypes'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const sub = (key: string, classification: string | null) => ({
  key,
  step_key: 'step-1',
  label: `Sub ${key}`,
  position: 0,
  lane_key: 'l',
  state: 'current',
  classification,
})

const base: any = {
  key: 'p',
  revision: 1,
  name: 'P',
  status: 'measured',
  lanes: [{ key: 'l', name: 'Owner', holder_kind: 'user', position: 0 }],
  steps: [{ key: 'step-1', lane_key: 'l', label: 'Quote', position: 0 }],
  edges: [],
  one_number: { step_key: 'step-1' },
  sub_steps: [sub('a', 'ai'), sub('b', 'by_hand'), sub('c', null)],
  edge_cases: [],
}

function mountBoard(plan: any) {
  return mount(PlannerLabelBoard, { props: { plan, busy: false }, global: { plugins: [i18n] } })
}

describe('PlannerLabelBoard', () => {
  it('asks for the one number first when none is chosen', () => {
    const w = mountBoard({ ...base, one_number: null })
    expect(w.find('[data-testid="label-needs-number"]').exists()).toBe(true)
  })

  it('groups sub-steps by label and lists the unlabelled ones with all three choices', () => {
    const w = mountBoard(base)
    expect(w.find('[data-testid="column-ai"]').text()).toContain('Sub a')
    expect(w.find('[data-testid="column-by_hand"]').text()).toContain('Sub b')
    expect(w.find('[data-testid="unlabelled"]').text()).toContain('Sub c')
    expect(w.findAll('[data-testid^="classify-c-"]')).toHaveLength(3)
  })

  it('emits the chosen label and the acknowledgement', async () => {
    const w = mountBoard(base)
    await w.find('[data-testid="classify-c-automation"]').trigger('click')
    await w.find('[data-testid="ack-by-hand"]').trigger('click')
    expect(w.emitted('classify')![0]).toEqual(['c', 'automation'])
    expect(w.emitted('acknowledge')).toHaveLength(1)
  })

  it('disables the acknowledgement once it was given', () => {
    const w = mountBoard({ ...base, by_hand_acknowledged_at: 't' })
    expect(w.find('[data-testid="ack-by-hand"]').attributes('disabled')).toBeDefined()
  })
})

describe('workflow plan helpers', () => {
  it('keeps existing sub-steps when adding one', () => {
    const body = breakdownWith(base, 'step-1', 'New')
    expect(body.sub_steps!.map((s) => s.label)).toEqual(['Sub a', 'Sub b', 'Sub c', 'New'])
    expect(body.sub_steps![0].classification).toBe('ai')
  })

  it('chains a new step after the last one', () => {
    const body = withStep(base, 'Next', 'l')
    expect(body.edges).toEqual([{ from_step: 'step-1', to_step: 'step-2' }])
  })

  it('treats only an HTTP 404 as not found, and unknown entry points as the org chart', () => {
    expect(isNotFoundError(new Error('HTTP 404: Not Found'))).toBe(true)
    expect(isNotFoundError(new Error('HTTP 500: x'))).toBe(false)
    expect(plannerEntryPoint('workflow_area')).toBe('workflow_area')
    expect(plannerEntryPoint('nope')).toBe('org_chart')
  })
})
