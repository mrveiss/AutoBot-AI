// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// The legacy (0-based) widget never shows a cancelled run as complete (#21106).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/services/api', () => ({ apiService: { get, delete: vi.fn() } }))
vi.mock('@/composables/usePollingJob', () => ({ usePollingJob: () => ({ start: vi.fn(), stop: vi.fn() }) }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: vi.fn() }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))

import WorkflowProgressWidget from '../WorkflowProgressWidget.vue'

const workflow = (over: Record<string, unknown>) => ({
  user_message: 'm', classification: 'c', estimated_duration: '1m', agents_involved: [],
  total_steps: 5, current_step: 1, status: 'running', steps: [], ...over,
})

async function render(w: unknown) {
  get.mockResolvedValue({ workflow: w })
  const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
  const m = mount(WorkflowProgressWidget, {
    props: { workflowId: 'wf-1' },
    global: { plugins: [i18n], stubs: { BaseButton: true, Icon: true } },
  })
  await flushPromises()
  return { text: m.find('.progress-text').text(), fill: m.find('.progress-fill').attributes('style') ?? '' }
}

describe('WorkflowProgressWidget step progress (#21106)', () => {
  beforeEach(() => get.mockReset())

  it('a completed run is 5/5 at 100%', async () => {
    const r = await render(workflow({ current_step: 4, status: 'completed' }))
    expect(r.text).toContain('5/5')
    expect(r.fill).toContain('width: 100%')
  })

  it('a cancelled run shows the step reached, no 100% bar', async () => {
    const r = await render(workflow({ current_step: 1, status: 'cancelled' }))
    expect(r.text).toContain('2/5')
    expect(r.fill).toContain('width: 20%')
  })
})
