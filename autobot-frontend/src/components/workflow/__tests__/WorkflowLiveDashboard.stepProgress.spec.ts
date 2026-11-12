// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Counter, bar and percent of a dashboard card come from one source (#21106).

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

vi.mock('@/composables/useEventBus', () => ({
  useEventBus: () => ({
    subscribe: vi.fn(() => vi.fn()),
    isConnected: { value: true },
    connectionState: { value: 'connected' },
    connect: vi.fn(),
  }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

import WorkflowLiveDashboard from '../WorkflowLiveDashboard.vue'

const step = (status: string) => ({ step_id: status, description: 'd', command: 'c', status })
const wf = (over: Record<string, unknown>) => ({
  workflow_id: 'wf-1', name: 'n', description: '', session_id: 's', current_step: 2, total_steps: 5,
  is_paused: false, is_cancelled: false, automation_mode: 'semi_automatic',
  started_at: '2026-11-08T10:00:00Z', steps: [step('completed'), step('executing')], ...over,
})

function card(w: unknown) {
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const m = mount(WorkflowLiveDashboard, {
    global: { plugins: [i18n] },
    props: { activeWorkflows: [w] as never, agentPerformance: {}, agentCapabilities: {}, loading: false, loadingCapabilities: false },
  })
  return {
    counter: m.find('.step-counter').text(),
    pct: m.find('.progress-pct').text(),
    width: m.find('.progress-fill').attributes('style') ?? '',
  }
}

describe('WorkflowLiveDashboard step progress (#21106)', () => {
  it('a running run: counter, bar and percent agree', () => {
    const c = card(wf({}))
    expect(c.counter).toContain('2')
    expect(c.pct).toBe('20%')
    expect(c.width).toContain('width: 20%')
  })

  it('a completed run is 5 / 5 at 100%', () => {
    const c = card(wf({ current_step: 6, completed_at: '2026-11-08T10:05:00Z', steps: [step('completed')] }))
    expect(c.counter).toContain('5')
    expect(c.pct).toBe('100%')
    expect(c.width).toContain('width: 100%')
  })

  it('a cancelled run shows the step reached, no 100% bar', () => {
    const c = card(wf({ is_cancelled: true, completed_at: '2026-11-08T10:05:00Z' }))
    expect(c.pct).toBe('20%')
    expect(c.width).toContain('width: 20%')
    expect(c.width).not.toContain('100%')
  })
})
