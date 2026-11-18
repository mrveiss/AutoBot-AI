// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19938 spec 7.5: gates G5-G7, approve, preview, convert and the refusals, on the real
// useWorkflowPlans composable with a mocked ApiClient.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()
vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post, put: vi.fn(), patch: vi.fn(), delete: vi.fn() }),
}))

const confirm = vi.fn()
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm }) }))

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: { companyId: 'co-1' } }),
  useRouter: () => ({ push }),
}))

import PlannerConvertStep from '../PlannerConvertStep.vue'
import { useWorkflowPlans } from '@/composables/llc/useWorkflowPlans'

const BASE = '/api/llc/company-os/workflow-plans/quote'
const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

const DRAFT = { workflow_id: 'wf-1', name: 'Quote the same day', owner_lane_key: 'lane-1', trigger_type: 'manual' }
const PREVIEW = { status: 'preview', workflows: [DRAFT], processes: [], contract_errors: [], preview_errors: [], turn_on: 'not_available' }

function plan(over: Record<string, unknown> = {}) {
  return {
    key: 'quote',
    revision: 1,
    name: 'Quote the same day',
    status: 'labeled',
    lanes: [{ key: 'lane-1', name: 'Owner', holder_kind: 'user', position: 0 }],
    conversion: null,
    ...over,
  }
}

function gate(missing: Array<{ gate: string; message: string; step?: string | null }>) {
  return { status: 'labeled', next_status: 'approved', missing }
}

function mountStep(p: Record<string, unknown>, g: ReturnType<typeof gate> | null) {
  return mount(PlannerConvertStep, {
    props: { plan: p as never, gate: g as never, api: useWorkflowPlans() },
    global: { plugins: [i18n] },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  confirm.mockResolvedValue(true)
})

describe('PlannerConvertStep gates', () => {
  it('names the missing criterion of a blocked gate and does not offer approval', async () => {
    const w = mountStep(plan(), gate([{ gate: 'G5', message: 'the owner has not acknowledged the By Hand sub-steps' }]))
    expect(w.find('[data-testid="gate-G5"]').attributes('data-state')).toBe('open')
    expect(w.find('[data-testid="gate-G5-missing"]').text()).toContain('has not acknowledged the By Hand')
    expect(w.find('[data-testid="gate-G1"]').attributes('data-state')).toBe('met')
    expect(w.find('[data-testid="gate-G7"]').attributes('data-state')).toBe('met')
    expect(w.find('[data-testid="convert-approve"]').exists()).toBe(false)
    expect(w.find('[data-testid="convert-preview"]').exists()).toBe(true)
  })

  it('re-reads the gate when the server refuses with 409, and says so instead of showing nothing', async () => {
    post.mockRejectedValue(new Error('HTTP 409: Conflict'))
    const w = mountStep(plan(), gate([{ gate: 'G6', message: 'no conversion preview exists yet: request one' }]))
    await w.find('[data-testid="convert-preview"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="convert-blocked"]').text()).toBe(en.llc.workflowPlanner.convert.blocked)
    expect(w.emitted('changed')).toEqual([[]])
  })
})

describe('PlannerConvertStep approve and convert', () => {
  it('previews, then approves through the confirm dialog and hands the approved plan up', async () => {
    const stored = plan({ conversion: PREVIEW })
    const w = mountStep(stored, gate([{ gate: 'G7', message: 'an owner or admin has not approved this preview' }]))
    expect(w.find('[data-testid="conversion-summary"]').attributes('data-status')).toBe('preview')
    expect(w.find('[data-testid="conversion-counts"]').text()).toBe('Workflows: 1. Processes: 0.')
    post.mockResolvedValue(plan({ status: 'approved', approved_at: 't', approved_by: 'owner', conversion: PREVIEW }))
    await w.find('[data-testid="convert-approve"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith(`${BASE}/approve`)
    const changed = w.emitted('changed') as Array<[{ status: string }]>
    expect(changed[0][0].status).toBe('approved')
  })

  it('does not approve when the owner cancels the confirmation', async () => {
    confirm.mockResolvedValue(false)
    const w = mountStep(plan({ conversion: PREVIEW }), gate([]))
    await w.find('[data-testid="convert-approve"]').trigger('click')
    await flushPromises()
    expect(post).not.toHaveBeenCalled()
  })

  it('converts an approved plan and shows the created workflows with a link', async () => {
    const approved = plan({ status: 'approved', conversion: PREVIEW })
    const w = mountStep(approved, { status: 'approved', next_status: 'converted', missing: [] } as never)
    post.mockResolvedValue(plan({ status: 'converted', conversion: { ...PREVIEW, status: 'committed' } }))
    await w.find('[data-testid="convert-create"]').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith(`${BASE}/convert`)
    const next = w.emitted('changed')?.[0]?.[0] as { status: string }
    expect(next.status).toBe('converted')
    await w.setProps({ plan: next as never })
    expect(w.find('[data-testid="conversion-summary"]').attributes('data-status')).toBe('committed')
    await w.find('[data-testid="open-workflows"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/llc/companies/co-1/automation')
    expect(w.find('[data-testid="turn-on-not-available"]').exists()).toBe(true)
  })

  it('shows the server reason when conversion fails, keeps the plan and re-reads it', async () => {
    post.mockRejectedValue(new Error('HTTP 500: conversion rolled back'))
    const w = mountStep(plan({ status: 'approved', conversion: PREVIEW }), null)
    await w.find('[data-testid="convert-create"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="convert-error"]').text()).toContain('conversion rolled back')
    expect(w.emitted('changed')).toEqual([[]])
    expect(w.find('[data-testid="convert-create"]').exists()).toBe(true)
  })

  it('reports a 404 as not available, not as an error', async () => {
    post.mockRejectedValue(new Error('HTTP 404: Not Found'))
    const w = mountStep(plan({ status: 'approved', conversion: PREVIEW }), null)
    await w.find('[data-testid="convert-create"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="convert-unavailable"]').text()).toBe(en.llc.workflowPlanner.convert.unavailable)
    expect(w.find('[data-testid="convert-error"]').exists()).toBe(false)
  })

  it('shows preview errors and withholds approval while the preview has any', async () => {
    const bad = { ...PREVIEW, preview_errors: ['node n1 has no outgoing transition'] }
    const w = mountStep(plan({ conversion: bad }), gate([{ gate: 'G6', message: 'node n1 has no outgoing transition' }]))
    expect(w.find('[data-testid="conversion-errors"]').text()).toContain('node n1 has no outgoing transition')
    expect(w.find('[data-testid="convert-approve"]').attributes('disabled')).toBeDefined()
  })
})

describe('PlannerConvertStep open criteria before approval', () => {
  it('disables Approve and names the open G5 criterion, without a confirm dialog', async () => {
    const w = mountStep(plan({ conversion: PREVIEW }), gate([{ gate: 'G5', message: 'the owner has not acknowledged the By Hand sub-steps' }]))
    const btn = w.find('[data-testid="convert-approve"]')
    expect(btn.attributes('disabled')).toBeDefined()
    const row = w.find('[data-testid="approve-blocker-G5"]').text()
    expect(row).toContain('By Hand list read and AI steps covered by approvals')
    expect(row).not.toMatch(/^G5/)
    expect(w.find('[data-testid="approve-blocker-G5-detail"]').text()).toContain('Server detail: the owner has not acknowledged')
    await btn.trigger('click')
    await flushPromises()
    expect(confirm).not.toHaveBeenCalled()
    expect(post).not.toHaveBeenCalled()
  })

  it('keeps Approve enabled when only G7 (the approval itself) is open, or no gate was read', async () => {
    const g7 = mountStep(plan({ conversion: PREVIEW }), gate([{ gate: 'G7', message: 'an owner or admin has not approved this preview' }]))
    expect(g7.find('[data-testid="convert-approve"]').attributes('disabled')).toBeUndefined()
    expect(g7.find('[data-testid="approve-blockers"]').exists()).toBe(false)
    const none = mountStep(plan({ conversion: PREVIEW }), null)
    expect(none.find('[data-testid="convert-approve"]').attributes('disabled')).toBeUndefined()
  })
})
