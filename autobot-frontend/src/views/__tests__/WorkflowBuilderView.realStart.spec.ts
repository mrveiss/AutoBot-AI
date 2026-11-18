// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Start with the REAL useWorkflowBuilder and mocked HTTP answers: the approval card appears only
// when the post-start status refresh confirms the start (#21043).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import StepApprovalCard from '@/components/workflow/StepApprovalCard.vue'

const route = reactive({ params: { section: 'runner' }, meta: {}, matched: [], query: {} })
const showToast = vi.fn()
const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

const step = (status: string) => ({ step_id: 's1', description: 'Restart nginx', command: 'x', status, risk_tier: 'high' })
const flow = (started: boolean) => ({
  workflow_id: 'wf-1', name: 'Flow', description: '', session_id: 's', current_step: 0, total_steps: 1,
  is_paused: false, is_cancelled: false, automation_mode: 'semi_automatic', user_interventions: [],
  ...(started ? { started_at: '2026-11-07T10:00:00Z' } : {}),
  steps: [step(started ? 'waiting_approval' : 'pending')],
})

vi.mock('@/utils/ApiClient', () => ({ default: http }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }))
vi.mock('@/composables/useWorkflowTemplates', () => ({ useWorkflowTemplates: () => ({ fetchTemplateDetail: vi.fn() }) }))
vi.mock('@/composables/useNotificationBus', () => ({ useNotificationBus: () => ({ showToast }) }))
vi.mock('@/composables/useWebSocket', () => ({ useWebSocket: () => ({ connect: vi.fn(), disconnect: vi.fn(), isConnected: { value: false } }) }))

import WorkflowBuilderView from '../WorkflowBuilderView.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })
const stubs = Object.fromEntries(['WorkflowTemplateGallery', 'WorkflowNotificationConfig', 'WorkflowHistory',
  'OrchestrationVisualizer', 'WorkflowLiveDashboard', 'GUIAutomationControls', 'ScreenCaptureViewer', 'VideoProcessor',
  'MediaGallery', 'PlanBeforeBuildingAction', 'RouterLink', 'WorkflowCanvas'].map((k) => [k, true]))
const toasts = (type: string) => showToast.mock.calls.filter((c) => c[1] === type).map((c) => c[0])

/** Status answers in order: the select sees not-started, then `afterStart` answers the refresh. */
function answerStatus(afterStart: () => Promise<unknown>) {
  let started = false
  http.post.mockImplementation(async () => { started = true; return { success: true } })
  http.get.mockImplementation(async (url: string) => {
    if (!url.includes('workflow_status')) throw new Error('not under test')
    return started ? afterStart() : { success: true, workflow: flow(false) }
  })
}
async function selectAndStart() {
  const w = mount(WorkflowBuilderView, { global: { plugins: [i18n], stubs, mocks: { $route: route } } })
  w.findComponent({ name: 'WorkflowRunner' }).vm.$emit('select-workflow', 'wf-1')
  await flushPromises()
  await w.findAll('button').find((b) => b.text() === 'Start')!.trigger('click')
  await flushPromises()
  return w
}

describe('WorkflowBuilderView start with the real composable (#21043)', () => {
  beforeEach(() => { vi.clearAllMocks(); route.params.section = 'runner' })

  it('a confirmed start shows the approval card and the started toast', async () => {
    answerStatus(async () => ({ success: true, workflow: flow(true) }))
    const w = await selectAndStart()
    expect(w.findAllComponents(StepApprovalCard)).toHaveLength(1)
    expect(toasts('success')).toEqual([en.workflow.builder.started])
  })

  it('a start whose status refresh fails is reported as unconfirmed, Start stays and no card shows', async () => {
    answerStatus(async () => { throw new Error('status unavailable') })
    const w = await selectAndStart()
    expect(toasts('warning')).toEqual([en.workflow.builder.startUnconfirmed])
    expect(toasts('success')).toEqual([])
    expect(w.findAllComponents(StepApprovalCard)).toHaveLength(0)
    expect(w.findAll('button').some((b) => b.text() === 'Start')).toBe(true)
  })
})
